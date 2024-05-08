from setuptools import setup, find_packages

requirements = [
    "PyYAML>=6.0.0,<7.0.0",
    "pytz>=2023.0,<2024.0",
    "pydantic>=2.0.0,<3.0.0"
    "pytest>=7.4.0,<8.0.0",
    "pytest-asyncio>=0.21.0,<0.22.0",
    "boto3>=1.28.0,<1.29.0",
    "pymongo>=4.4.0,<4.5.0",
    "tqdm>=4.66.0,<4.67.0",
    "fastapi>=0.100.0,<0.200.0",
    "uvicorn[standard]",
    "requests>=2.0.0,<3.0.0",
    "tcxreader>=0.4.0,<0.5.0",
    "python-multipart>=0.0.8,<0.1.0",
    "notion-client>=2.2.0,<2.3.0",

    # File metadata extraction
    "exifread>=3.0.0,<4.0.0",
    "ffmpeg-python>=0.2.0,<0.3.0",  # ffmpeg-python is a wrapper around ffmpeg. Must install ffmpeg separately.
    "python-dateutil>=2.9.0.post0,<3.0.0",
    "PyPDF2>=3.0.0<4.0.0",
    "python-magic>=0.4.20,<0.5.0",  # python-magic is a wrapper around libmagic. Must install libmagic separately. https://github.com/ahupp/python-magic
]

setup(
    name='jserver',
    version='0.0.1',
    packages=find_packages(),
    install_requires=requirements,
)
