from setuptools.command.install import install
from setuptools import setup, find_packages
import subprocess
import os

class PostInstallCommand(install):
    def run(self):
        install.run(self)
        # Ensure the spaCy model is downloaded
        subprocess.check_call([self.install_scripts, 'post_install.py'])

setup(
    name='seo-bhishma-cli',
    version='1.3',
    author='Hitendra Rathore',
    author_email='hitendra1995@mail.com',
    description='A CLI tool for SEO tasks',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/anonymousraft/seo-bhishma-cli.git',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'click',
        'requests',
        'pandas',
        'tqdm',
        'beautifulsoup4',
        'art',
        'fake_useragent',
        'lxml',
        'scikit-learn',
        'openai',
        'pyyaml',
        'rich',
        'google-auth',
        'google-auth-oauthlib',
        'google-api-python-client',
        'numpy',
        'spacy'
    ],
    entry_points={
        'console_scripts': [
            'seo-bhishma-cli=seo_bhishma_cli.cli:cli',
        ],
    },
    cmdclass={
        'install': PostInstallCommand,
    },
    scripts=['post_install.py'],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6'
)
