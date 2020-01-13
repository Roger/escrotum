from setuptools import setup

setup(
    name="escrotum",
    version="1.0.1",
    author='Roger Duran',
    author_email='rogerduran@gmail.com',
    url='https://github.com/Roger/escrotum',
    download_url='https://github.com/Roger/escrotum/archive/1.0.1.tar.gz',
    keywords=['screenshot', 'screen-recording', 'scrot', 'cli'],
    packages=["escrotum"],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
      'gobject',
      'xcffib',
    ],
    entry_points={
        'console_scripts': [
            'escrotum = escrotum.main:run',
        ],
    }
)
