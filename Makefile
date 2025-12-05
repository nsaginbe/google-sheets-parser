all: format static

format:
	black app
	isort app

static:
	flake8 app
	mypy app