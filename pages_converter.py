import zipfile
import os
from unidecode import unidecode
from iwork_to_text import IWAFile

def convert_pages_to_txt(pages_file, txt_file):
    with zipfile.ZipFile(pages_file, 'r') as z:
        iwa_files = [f for f in z.namelist() if f.endswith('.iwa')]
        text_content = []

        for iwa_file in iwa_files:
            with z.open(iwa_file) as f:
                iwa_data = f.read()
                iwa = IWAFile(iwa_data)
                text_content.append(iwa.extract_text())

        with open(txt_file, 'w', encoding='utf-8') as txt_f:
            for content in text_content:
                txt_f.write(unidecode(content))
                txt_f.write('\n')

pages_file = "C:\\Users\\Astana\\Desktop\\Client\\тост.pages"
txt_file = "C:\\Users\\Astana\\Desktop\\Client\\тост.txt"
convert_pages_to_txt(pages_file, txt_file)

