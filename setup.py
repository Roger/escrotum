from setuptools import setup

setup(
    name="escrotum",
    version="0.2.1",
    author='Roger Duran',
    author_email='rogerduran@gmail.com',
    url='https://github.com/Roger/escrotum',
    download_url='https://github.com/Roger/escrotum/archive/0.2.1.tar.gz',
    keywords=['screenshot', 'scrot', 'cli'],
    packages=["escrotum"],
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'escrotum = escrotum.main:run',
        ],
    }
)
