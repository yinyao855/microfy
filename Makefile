.PHONY: refresh build install build_dist json release lint test clean

refresh: clean build install lint

build:
	python -m build

install:
	pip install .

build_dist:
	make clean
	python setup.py sdist bdist_wheel
	pip install dist/*.whl

release:
	python -m twine upload dist/*

test:
	python -m unittest

clean:
	rm -rf __pycache__
	rm -rf tests/__pycache__
	rm -rf src/microfy/__pycache__
	rm -rf build
	rm -rf dist
	rm -rf microfy.egg-info
	rm -rf src/microfy.egg-info
	pip uninstall -y microfy