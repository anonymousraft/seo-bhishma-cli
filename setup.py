from setuptools import setup, find_packages
import os

def read_requirements():
    req_file_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(req_file_path, 'r', encoding='utf-8', newline='') as req_file:
        requirements = req_file.read().splitlines()
        requirements = [req.strip() for req in requirements if req.strip() and not req.startswith('#')]
        return requirements

setup(
    name='seo-bhishma-cli',
    version='1.4.2',
    author='Hitendra Rathore',
    author_email='hitendra1995@mail.com',
    description='A CLI tool for SEO tasks',
    long_description=open('README.md').read(),
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
