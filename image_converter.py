from PIL import Image, ImageFilter, UnidentifiedImageError
from wand.image import Image as WandImage
from pathlib import Path
import shutil
import os
from enum import Enum
from send2trash import send2trash
import copy
import functools
from fpdf import FPDF

# python C:\Users\bolat\Desktop\my_programs\image_converter.py


"""
jpeg -> jpeg (jpeg из соц. сетей не редактируется в фотошопе, если прогнать через PIL - редактируется)

heic -> jpeg (heic не поддерживается фотошопом и программами для печати)

png -> webp -> tiff (png не поддерживается программами для печати.
для сохранения прозрачного фона используем конвертиацию в webp, а потом в tiff.
Прямая конвертация в tiff вызывает искажения фона)

webp -> tiff (webp не поддерживается фотошопом и программами для печати.
для сохранения прозрачного фона используем конвертиацию в tiff)

"""


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
	mime_type  = None
	to_type = None

	def __init__(self, path_: Path = 'C:/Users/bolat/Desktop/Client/'):
		self.path_ = path_

	def _get_images(self):
		"""interface method"""
		images = self.path_.glob(self.mime_type)
		return images

	def _image_converting(self, img_path: Path):
		img = Image.open(img_path)
		img.save(self.path_.joinpath(img_path.stem + self.to_type))

	@progress_checker(start=f'Конвертируем фотографии из {mime_type} в {to_type}')
	def mass_converting(self):
		images = self._get_images()
		for img in images:
			print(img)
			self._image_converting(img)

	def _delete_img(self, img_path: Path):
		try:
			send2trash(img_path)
		except Exception as exx:
			print(exx)

	def mass_deleting(self):
		images = self._get_images()
		for img in images:
			self._delete_img(img)


class JpegToJpegConverter(ImageConverter):
	mime_type  = ImagesTypes.JPEG.value
	to_type = ImagesTypes.JPEG.value[1:]


class JpegToPDFConverter(ImageConverter):
	mime_type  = ImagesTypes.PDF.value
	to_type = ImagesTypes.PDF.value[:3]

	def _image_converting(self, img_path: Path):
		img_path = str(img_path)
		try:
			image = Image.open(img_path)
		except UnidentifiedImageError:
			pass
		else:
			pdf = FPDF()
			pdf.add_page()
			pdf.set_auto_page_break(auto=True, margin=15)
			pdf.image(img_path, x=10, y=10, w=pdf.w - 20)
			
			img_path = Path(img_path)
			pdf.output(self.path_.joinpath(img_path.stem + '.' + self.to_type))


class GifToJpegConverter(ImageConverter):
	mime_type  = ImagesTypes.GIF.value
	to_type = ImagesTypes.JPEG.value[1:]


class PngToWebpConverter(ImageConverter):
	mime_type  = ImagesTypes.PNG.value
	to_type = ImagesTypes.WEBP.value[1:]


class WebpToTiffConverter(ImageConverter):
	mime_type  = ImagesTypes.WEBP.value
	to_type = ImagesTypes.TIFF.value[1:]


class TiffToJpegConverter(ImageConverter):
	mime_type  = ImagesTypes.TIFF.value
	to_type = ImagesTypes.JPEG.value[1:]


class HeicToJpegConverter(ImageConverter):
	mime_type = AppleImagesTypes
	to_type = ImagesTypes.JPEG.value[1:]

	def _get_images(self):
		images = []
		types = [x.value for x in self.mime_type]
		for type_ in types:
			imgs = self.path_.glob(type_)
			images.extend(imgs)
		return images

	def _image_converting(self, img_path: Path):
		img = WandImage(filename=img_path)
		img.format='jpg'
		img.save(filename=self.path_.joinpath(img_path.stem + self.to_type))
		img.close()


if __name__ == '__main__':
	path = Path('C:\\Users\\bolat\\Desktop\\Client')
	# path = Path('C:\\Users\\bolat\\Desktop\\Client\\WhatsApp Unknown 2023-04-17 at 14.44.37')
	# path.joinpath('радик')

	JpegToJpegConverter(path).mass_converting()
	GifToJpegConverter(path).mass_converting()
	JpegToPDFConverter(path).mass_converting()

	heic_files = HeicToJpegConverter(path)
	heic_files.mass_converting()
	heic_files.mass_deleting()

	png_files = PngToWebpConverter(path)
	png_files.mass_converting()
	png_files.mass_deleting()

	webp_files = WebpToTiffConverter(path)
	webp_files.mass_converting()
	webp_files.mass_deleting()



def convert_jpg_to_pdf(image_path, pdf_path):
    image = Image.open(image_path)
    pdf = PdfWriter()

    pdf.add_page()
    pdf.add_image(image, 0, 0, image.width, image.height)

    with open(pdf_path, "wb") as output:
        pdf.write(output)
