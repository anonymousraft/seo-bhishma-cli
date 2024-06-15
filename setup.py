from setuptools import setup, find_packages

setup(
    name='seo-bhishma-cli',
    version='0.1.0',
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
        'art'
    ],
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
    python_requires='>=3.6',
)
