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

# Регистрируем поддержку HEIC в PIL
register_heif_opener()


class ImagesTypes(Enum):
	JPG = '*.JPG'
	JPEG = '*.jpeg'
	PNG = '*.png'
	WEBP = '*.webp'
	TIFF = '*.tiff'
	GIF = '*.gif'
	AVIF = '*.avif'
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
		
		# Устанавливаем mime_type
		if from_format == 'ALL':
			self.mime_type = None  # Будем обрабатывать все
		elif from_format == 'HEIC':
			self.mime_type = None  # Специальная обработка для HEIC
		else:
			self.mime_type = f'*.{from_format.lower()}'
		
		# Устанавливаем to_type
		self.to_type = f'.{to_format.lower()}'
	
	def _get_images(self):
		"""Получаем список изображений для конвертации"""
		if self.from_format == 'ALL':
			# Собираем все поддерживаемые форматы
			all_formats = ['*.jpg', '*.JPG', '*.jpeg', '*.JPEG', '*.png', '*.PNG', 
			               '*.webp', '*.WEBP', '*.tiff', '*.TIFF', '*.gif', '*.GIF', 
			               '*.avif', '*.AVIF', '*.heic', '*.HEIC']
			images = []
			for fmt in all_formats:
				images.extend(self.path_.glob(fmt))
			return images
		elif self.from_format.upper() == 'HEIC':
			# Обрабатываем оба варианта написания HEIC
			images = []
			images.extend(self.path_.glob('*.heic'))
			images.extend(self.path_.glob('*.HEIC'))
			return images
		else:
			return self.path_.glob(self.mime_type)
	
	def _image_converting(self, img_path: Path):
		"""Конвертируем изображение"""
		try:
			img = Image.open(img_path)
			
			# Определяем целевой формат
			target_format = self.to_format.upper().replace('.', '')
			
			# Если целевой формат JPEG, конвертируем в RGB
			if target_format in ['JPEG', 'JPG']:
				if img.mode in ('RGBA', 'LA', 'P'):
					background = Image.new('RGB', img.size, (255, 255, 255))
					background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
					img = background
				elif img.mode != 'RGB':
					img = img.convert('RGB')
				img.save(self.path_.joinpath(img_path.stem + self.to_type), 'JPEG', quality=95)
			
			# Если целевой формат PNG и нужна прозрачность
			elif target_format == 'PNG':
				if img.mode not in ('RGBA', 'LA', 'P', 'RGB'):
					img = img.convert('RGBA')
				img.save(self.path_.joinpath(img_path.stem + self.to_type), 'PNG')
			
			# Если целевой формат TIFF
			elif target_format in ['TIFF', 'TIF']:
				img.save(self.path_.joinpath(img_path.stem + self.to_type), 'TIFF')
			
			else:
				# Для остальных форматов
				img.save(self.path_.joinpath(img_path.stem + self.to_type))
				
		except Exception as e:
			raise Exception(f"Ошибка при конвертации {img_path.name}: {e}")


class ConversionScreen(Screen):
	"""Экран выбора конвертации"""
	
	CSS = """
	ConversionScreen {
		align: center middle;
	}
	
	#main_wrapper {
		width: 100%;
		height: auto;
	}
	
	#main_container {
		width: 52;
		height: 26;
		border: solid $primary;
		padding: 1 2;
	}
	
	#status_container {
		width: 28;
		height: 26;
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
	
	#path_input {
		width: 100%;
		margin: 0 0 1 0;
	}
	
	.format_container {
		width: 1fr;
		height: 13;
		border: solid $secondary;
		padding: 1;
		margin: 0 1;
		overflow-y: auto;
	}
	
	RadioButton {
		margin: 0 1;
		height: 1;
	}
	
	#button_container {
		align: center middle;
		margin: 0;
		height: auto;
	}
	
	Button {
		margin: 0 1;
		min-width: 16;
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
				yield Input(placeholder="C:/Users/username/Desktop/images", id="path_input")
				
				yield Label("Выберите формат конвертации:", classes="section-title")
				
				with Horizontal():
					with Vertical(classes="format_container"):
						yield Label("ИЗ формата:", classes="section-title")
						with RadioSet(id="from_format"):
							yield RadioButton("JPG", id="from_jpg")
							yield RadioButton("JPEG", id="from_jpeg")
							yield RadioButton("PNG", id="from_png")
							yield RadioButton("WEBP", id="from_webp")
							yield RadioButton("TIFF", id="from_tiff")
							yield RadioButton("GIF", id="from_gif")
							yield RadioButton("AVIF", id="from_avif")
							yield RadioButton("HEIC", id="from_heic")
							yield RadioButton("ALL (все форматы)", id="from_all", value=True)
					
					with Vertical(classes="format_container"):
						yield Label("В формат:", classes="section-title")
						with RadioSet(id="to_format"):
							yield RadioButton("JPEG", id="to_jpeg", value=True)
							yield RadioButton("PNG", id="to_png")
							yield RadioButton("TIFF", id="to_tiff")
				
				with Horizontal(id="button_container"):
					yield Button("🚀 Конвертировать", variant="success", id="convert_btn")
					yield Button("🗑️  + Удалить", variant="warning", id="convert_delete_btn")
					yield Button("❌ Выход", variant="error", id="exit_btn")
			
			with Vertical(id="status_container"):
				yield Label("📊 Статус:", classes="section-title")
				yield Static("Ожидание...", id="status_box")
		
		yield Footer()
	
	def on_mount(self) -> None:
		"""При монтировании экрана"""
		self.query_one("#path_input").focus()
		self.status_text = ""  # Инициализируем переменную для хранения текста статуса
	
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