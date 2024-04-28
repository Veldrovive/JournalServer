from setuptools import setup, find_packages

requirements = [
    "PyYAML>=6.0.0,<7.0.0",
    "pytz>=2023.0,<2024.0",
    "pydantic>=2.0.0,<3.0.0"
    "pytest>=7.4.0,<8.0.0",
    "pytest-asyncio>=0.21.0,<0.22.0",
    "Pillow>=10.0.0,<11.0.0",
    "boto3>=1.28.0,<1.29.0",
    "pymongo>=4.4.0,<4.5.0",
    "tqdm>=4.66.0,<4.67.0",
    "fastapi>=0.100.0,<0.200.0",
    "uvicorn[standard]",
    "rumps>=0.4.0,<0.5.0",
    "requests>=2.0.0,<3.0.0",
    "tcxreader>=0.4.0,<0.5.0",
    "python-multipart>=0.0.8"
]

setup(
    name='jserver',
    version='0.0.1',
    packages=find_packages(),
    install_requires=requirements,
)
