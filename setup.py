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
    version='2.0.0',
    author='Hitendra Rathore',
    author_email='hitendra1995@mail.com',
    description='A CLI tool for SEO tasks including sitemap downloading, indexing checks, backlink live checks, and more.',
    long_description=read_readme(),
    long_description_content_type='text/markdown',
    url='https://github.com/anonymousraft/seo-bhishma-cli',
    packages=find_packages(exclude=['tests*']),
    include_package_data=True,
    install_requires=read_requirements(),
    entry_points={
        'console_scripts': [
            'seo-bhishma-cli=seo_bhishma_cli.cli:cli',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Topic :: Software Development :: Build Tools',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
    project_urls={
        'Documentation': 'https://github.com/anonymousraft/seo-bhishma-cli#readme',
        'Source': 'https://github.com/anonymousraft/seo-bhishma-cli',
        'Tracker': 'https://github.com/anonymousraft/seo-bhishma-cli/issues',
    },
    keywords='SEO, CLI, sitemap, indexing, backlinks',
    license='MIT',
    zip_safe=False,
)
