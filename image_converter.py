from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
from pathlib import Path
from enum import Enum
from send2trash import send2trash
import functools
from fpdf import FPDF
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Label, Input, RadioButton, RadioSet
from textual.screen import Screen
from textual import on
import rawpy
import numpy as np
import subprocess
import io

# Регистрируем поддержку HEIC в PIL
register_heif_opener()


class ImagesTypes(Enum):
	JPG = '*.JPG'
	JPEG = '*.jpeg'
	PNG = '*.png'
	WEBP = '*.webp'
	TIFF = '*.tiff'
	TIF = '*.tif'
	GIF = '*.gif'
	AVIF = '*.avif'
	DNG = '*.dng'
	PDF = 'pdf_*'


class AppleImagesTypes(Enum):
	HEIC_SMALL = '*.heic'
	HEIC_LARGE = '*.HEIC'


def progress_checker(start: str, finish: str = '	✓'):
	"""
	Декоратор для отслеживания прогресса выполнения программы
	start - сообщение перед выполнением функции
	finish - сообщение после выполнения функции
	"""
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			print(start, end='')
			val = func(*args, **kwargs)
			print(finish)
			return val
		return wrapper
	return decorator


class ImageConverter:
	"""Interface to another converter classes"""
	mime_type = None
	to_type = None

	def __init__(self, path_: Path = 'C:/Users/bolat/Desktop/Client/'):
		self.path_ = Path(path_)

	def _get_images(self):
		"""interface method"""
		images = self.path_.glob(self.mime_type)
		return images

	def _image_converting(self, img_path: Path):
		img = Image.open(img_path)
		img.save(self.path_.joinpath(img_path.stem + self.to_type))

	def mass_converting(self, callback=None):
		images = list(self._get_images())
		total = len(images)
		
		if total == 0:
			if callback:
				callback(f"⚠ Не найдено файлов формата {self.mime_type}")
			return
		
		for idx, img in enumerate(images, 1):
			if callback:
				callback(f"Конвертируем ({idx}/{total}): {img.name}")
			try:
				self._image_converting(img)
			except Exception as e:
				if callback:
					callback(f"⚠ Ошибка при конвертации {img.name}: {e}")
		
		if callback:
			callback(f"✓ Конвертировано {total} файлов из {self.mime_type} в {self.to_type}")

	def _delete_img(self, img_path: Path):
		try:
			send2trash(img_path)
		except Exception as exx:
			print(exx)

	def mass_deleting(self, callback=None):
		images = list(self._get_images())
		for img in images:
			self._delete_img(img)
		if callback and len(images) > 0:
			callback(f"✓ Удалено {len(images)} исходных файлов")


class UniversalConverter(ImageConverter):
	"""Универсальный конвертер для любых форматов"""
	
	def __init__(self, path_: Path, from_format: str, to_format: str):
		super().__init__(path_)
		self.from_format = from_format.lower()
		self.to_format = to_format.lower()
		self.mime_type = f'*.{from_format.lower()}'
		self.to_type = f'.{to_format.lower()}'
	
	def _get_images(self):
		"""Получаем список изображений без дубликатов (case-insensitive через stem)"""
		patterns = {
			'all':        ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.tiff',
			               '*.tif', '*.gif', '*.avif', '*.heic', '*.dng'],
			'heic':       ['*.heic'],
			'tif':        ['*.tif', '*.tiff'],
			'tiff':       ['*.tif', '*.tiff'],
			'dng':        ['*.dng'],
		}
		fmt = self.from_format
		glob_list = patterns.get(fmt, [f'*.{fmt}'])
		
		seen = set()
		images = []
		for pattern in glob_list:
			# glob без учёта регистра: собираем оба варианта
			for p in [pattern, pattern.upper()]:
				for f in self.path_.glob(p):
					key = f.resolve()
					if key not in seen:
						seen.add(key)
						images.append(f)
		return images

	@staticmethod
	def _open_dng(img_path: Path) -> Image.Image:
		"""
		Открываем DNG файл (в т.ч. iPhone ProRAW) несколькими методами по цепочке:
		  1. tifffile + imagecodecs — читает LJPEG/LinearDNG (iPhone ProRAW, Adobe DNG)
		     Ищет страницу с полным изображением (SubfileType=0) или preview (SubfileType=1)
		  2. rawpy.postprocess() — для классических Bayer RAW DNG
		  3. rawpy.extract_thumb() — встроенный JPEG превью
		  4. PIL как TIFF — простой fallback
		  5. dcraw через subprocess — последний резерв
		"""
		errors = []

		# Метод 1: tifffile + imagecodecs (лучший для iPhone ProRAW / LinearDNG)
		try:
			import tifffile
			import numpy as np

			with tifffile.TiffFile(str(img_path)) as tif:
				# Собираем все страницы с их метаданными
				pages_info = []
				for i, page in enumerate(tif.pages):
					tags = {tag.name: tag.value for tag in page.tags.values()}
					subfile = tags.get('NewSubfileType', tags.get('SubfileType', -1))
					photo = tags.get('PhotometricInterpretation', -1)
					w = tags.get('ImageWidth', 0)
					h = tags.get('ImageLength', 0)
					pages_info.append((i, page, subfile, photo, w, h))

				# Приоритет 1: полное RGB изображение (SubfileType=0, photometric=RGB/YCbCr)
				# Приоритет 2: preview (SubfileType=1)
				# Приоритет 3: любая читаемая страница
				best_page = None
				for priority, subfile_target in [(0, 0), (1, 1), (2, -1)]:
					for i, page, subfile, photo, w, h in pages_info:
						if priority == 2 or subfile == subfile_target:
							try:
								data = page.asarray()
								if data.ndim == 3 and data.shape[2] in (3, 4):
									best_page = data
									break
								elif data.ndim == 2:
									best_page = data
									break
							except Exception:
								continue
					if best_page is not None:
						break

			if best_page is not None:
				arr = best_page
				# Нормализуем 16-bit в 8-bit
				if arr.dtype == np.uint16:
					arr = (arr / 256).astype(np.uint8)
				elif arr.dtype != np.uint8:
					arr = arr.astype(np.uint8)
				# Убираем альфа-канал если есть
				if arr.ndim == 3 and arr.shape[2] == 4:
					arr = arr[:, :, :3]
				return Image.fromarray(arr)
		except Exception as e:
			errors.append(f"tifffile: {e}")

		# Метод 2: rawpy полное RAW-декодирование
		try:
			with rawpy.imread(str(img_path)) as raw:
				rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
			return Image.fromarray(rgb)
		except Exception as e:
			errors.append(f"rawpy.postprocess: {e}")

		# Метод 3: rawpy встроенный превью (thumbnail)
		try:
			with rawpy.imread(str(img_path)) as raw:
				thumb = raw.extract_thumb()
			if thumb.format == rawpy.ThumbFormat.JPEG:
				return Image.open(io.BytesIO(bytes(thumb.data)))
			elif thumb.format == rawpy.ThumbFormat.BITMAP:
				return Image.fromarray(thumb.data)
		except Exception as e:
			errors.append(f"rawpy.extract_thumb: {e}")

		# Метод 4: PIL как TIFF (DNG — расширение TIFF формата)
		try:
			from PIL import TiffImagePlugin
			with open(img_path, 'rb') as f:
				data = f.read()
			img = Image.open(io.BytesIO(data))
			img.load()
			return img
		except Exception as e:
			errors.append(f"PIL/TIFF: {e}")

		# Метод 5: dcraw через subprocess
		try:
			result = subprocess.run(
				['dcraw', '-c', '-w', '-T', str(img_path)],
				capture_output=True, timeout=120
			)
			if result.returncode == 0 and result.stdout:
				return Image.open(io.BytesIO(result.stdout))
			errors.append(f"dcraw: exit={result.returncode}, {result.stderr.decode(errors='replace')[:100]}")
		except FileNotFoundError:
			errors.append("dcraw: не установлен")
		except Exception as e:
			errors.append(f"dcraw: {e}")

		raise RuntimeError("Все методы не сработали:\n  " + "\n  ".join(errors))

	def _image_converting(self, img_path: Path):
		"""Конвертируем изображение"""
		try:
			if img_path.suffix.lower() == '.dng':
				img = self._open_dng(img_path)
			else:
				img = Image.open(img_path)
			
			target_format = self.to_format.upper().replace('.', '')
			out_path = self.path_.joinpath(img_path.stem + self.to_type)
			
			if target_format in ['JPEG', 'JPG']:
				if img.mode in ('RGBA', 'LA', 'P'):
					background = Image.new('RGB', img.size, (255, 255, 255))
					background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
					img = background
				elif img.mode != 'RGB':
					img = img.convert('RGB')
				img.save(out_path, 'JPEG', quality=95)
			
			elif target_format == 'PNG':
				if img.mode not in ('RGBA', 'LA', 'P', 'RGB'):
					img = img.convert('RGBA')
				img.save(out_path, 'PNG')
			
			elif target_format in ['TIFF', 'TIF']:
				img.save(out_path, 'TIFF')
			
			else:
				img.save(out_path)
				
		except Exception as e:
			raise Exception(f"Ошибка при конвертации {img_path.name}: {e}")


class ConversionScreen(Screen):
	"""Экран выбора конвертации"""
	
	CSS = """
	ConversionScreen {
		align: center middle;
	}
	
	#main_wrapper {
		width: auto;
		height: auto;
	}
	
	#main_container {
		width: 72;
		height: 29;
		border: solid $primary;
		padding: 1 2;
	}
	
	#status_container {
		width: 40;
		height: 29;
		border: solid $warning;
		padding: 1;
		margin-left: 1;
	}
	
	.title {
		text-align: center;
		text-style: bold;
		color: $accent;
		margin: 0 0;
	}
	
	.section-title {
		text-style: bold;
		color: $success;
		margin: 0 0;
	}
	
	#path_input_container {
		width: 100%;
		height: auto;
		margin: 0 0 1 0;
	}
	
	#path_input {
		width: 1fr;
		margin: 0;
	}
	
	#clear_path_btn {
		width: 8;
		margin-left: 1;
	}
	
	.format_container {
		width: 1fr;
		height: 17;
		border: solid $secondary;
		padding: 1;
		margin: 0 0;
		overflow-y: auto;
	}
	
	RadioButton {
		margin: 0 1;
		height: 1;
	}
	
	#button_container {
		align: center middle;
		margin: 0 1;
		height: auto;
	}
	
	Button {
		margin: 0 1;
		min-width: 2;
		height: 3;
	}
	
	#status_box {
		width: 100%;
		height: 100%;
		padding: 0;
		margin: 0;
		overflow-y: scroll;
	}
	"""
	
	def compose(self) -> ComposeResult:
		yield Header()
		
		with Horizontal(id="main_wrapper"):
			with Container(id="main_container"):
				yield Label("🖼️  IMAGE CONVERTER", classes="title")
				
				yield Label("Путь к папке с изображениями:", classes="section-title")
				
				with Horizontal(id="path_input_container"):
					yield Input(placeholder="C:/Users/username/Desktop/images", id="path_input")
					yield Button("🗑️", id="clear_path_btn", variant="primary")
				
				yield Label("Выберите формат конвертации:", classes="section-title")
				
				with Horizontal():
					with Horizontal(classes="format_container"):
						yield Label("ИЗ формата:", classes="section-title")
						with RadioSet(id="from_format"):
							yield RadioButton("JPG", id="from_jpg")
							yield RadioButton("JPEG", id="from_jpeg")
							yield RadioButton("PNG", id="from_png")
							yield RadioButton("WEBP", id="from_webp")
							yield RadioButton("TIFF", id="from_tiff")
							yield RadioButton("TIF", id="from_tif")
							yield RadioButton("GIF", id="from_gif")
							yield RadioButton("AVIF", id="from_avif")
							yield RadioButton("HEIC", id="from_heic")
							yield RadioButton("DNG", id="from_dng")
							yield RadioButton("ALL (все форматы)", id="from_all", value=True)
					
					with Horizontal(classes="format_container"):
						yield Label("В формат:", classes="section-title")
						with RadioSet(id="to_format"):
							yield RadioButton("JPEG", id="to_jpeg", value=True)
							yield RadioButton("PNG", id="to_png")
							yield RadioButton("TIFF", id="to_tiff")
							yield RadioButton("TIF", id="to_tif")
				
				with Horizontal(id="button_container"):
					yield Button("🚀 Конвертировать + 🗑️", variant="warning", id="convert_delete_btn")
					yield Button("🚀 Конвертировать", variant="success", id="convert_btn")
		
			with Vertical(id="status_container"):
				yield Label("📊 Статус:", classes="section-title")
				yield Static("Ожидание...", id="status_box")
		
		yield Footer()
	
	def on_mount(self) -> None:
		"""При монтировании экрана"""
		self.query_one("#path_input").focus()
		self.status_text = ""  # Инициализируем переменную для хранения текста статуса
	
	@on(Button.Pressed, "#clear_path_btn")
	def clear_path(self) -> None:
		"""Очистить путь к папке"""
		path_input = self.query_one("#path_input", Input)
		path_input.value = ""
		path_input.focus()
	
	@on(Button.Pressed, "#convert_btn")
	def convert_images(self) -> None:
		"""Конвертировать изображения"""
		self._perform_conversion(delete_originals=False)
	
	@on(Button.Pressed, "#convert_delete_btn")
	def convert_and_delete_images(self) -> None:
		"""Конвертировать и удалить оригиналы"""
		self._perform_conversion(delete_originals=True)
	
	def _perform_conversion(self, delete_originals: bool = False) -> None:
		"""Выполнить конвертацию"""
		path_input = self.query_one("#path_input", Input)
		status_box = self.query_one("#status_box", Static)
		
		path_str = path_input.value.strip()
		
		if not path_str:
			status_box.update("⚠ Ошибка: Укажите путь к папке!")
			return
		
		path = Path(path_str)
		
		if not path.exists():
			status_box.update(f"⚠ Ошибка: Папка не найдена: {path}")
			return
		
		if not path.is_dir():
			status_box.update(f"⚠ Ошибка: Указанный путь не является папкой: {path}")
			return
		
		# Получаем выбранные форматы
		from_format_radio = self.query_one("#from_format", RadioSet)
		to_format_radio = self.query_one("#to_format", RadioSet)
		
		from_format = from_format_radio.pressed_button.id.replace("from_", "").upper()
		to_format = to_format_radio.pressed_button.id.replace("to_", "").upper()
		
		if from_format == "ALL":
			from_format_display = "ALL (все форматы)"
		else:
			from_format_display = from_format
		
		# Обновляем статус
		self.status_text = f"📁 Папка: {path}\n"
		self.status_text += f"🔄 Конвертация: {from_format_display} → {to_format}\n"
		self.status_text += f"{'🗑️  С удалением оригиналов' if delete_originals else '📦 Без удаления оригиналов'}\n"
		self.status_text += "=" * 60 + "\n"
		status_box.update(self.status_text)
		
		def update_status(message: str):
			"""Колбэк для обновления статуса"""
			self.status_text += message + "\n"
			status_box.update(self.status_text)
		
		try:
			# Создаем универсальный конвертер
			converter = UniversalConverter(path, from_format, to_format)
			
			# Конвертируем
			update_status("\n🚀 Начинаем конвертацию...")
			converter.mass_converting(callback=update_status)
			
			# Удаляем оригиналы если нужно
			if delete_originals:
				update_status("\n🗑️  Удаляем исходные файлы...")
				converter.mass_deleting(callback=update_status)
			
			update_status("\n✅ ГОТОВО! Конвертация завершена успешно!")
			
		except Exception as e:
			update_status(f"\n❌ ОШИБКА: {e}")
	
	@on(Button.Pressed, "#exit_btn")
	def exit_app(self) -> None:
		"""Выход из приложения"""
		self.app.exit()


class ImageConverterApp(App):
	"""Приложение для конвертации изображений"""
	
	TITLE = "Image Converter TUI"
	BINDINGS = [
		("q", "quit", "Выход"),
	]
	
	def on_mount(self) -> None:
		"""При запуске приложения"""
		self.push_screen(ConversionScreen())


if __name__ == '__main__':
	app = ImageConverterApp()
	app.run()