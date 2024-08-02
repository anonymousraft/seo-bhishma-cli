from setuptools import setup, find_packages
from pathlib import Path

def read_requirements():
    req_file_path = Path(__file__).parent / 'requirements.txt'
    with req_file_path.open('r', encoding='utf-8') as req_file:
        requirements = req_file.read().splitlines()
        requirements = [req.strip() for req in requirements if req.strip() and not req.startswith('#')]
        return requirements

def read_readme():
    readme_file_path = Path(__file__).parent / 'README.md'
    with readme_file_path.open('r', encoding='utf-8') as readme_file:
        return readme_file.read()

setup(
    name='seo-bhishma-cli',
    version='1.5.1',
    author='Hitendra Rathore',
    author_email='hitendra1995@mail.com',
    description='A CLI tool for SEO tasks',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    url='https://github.com/anonymousraft/seo-bhishma-cli.git',
    packages=find_packages(),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'seo-bhishma-cli=seo_bhishma_cli.cli:cli',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6'
)
