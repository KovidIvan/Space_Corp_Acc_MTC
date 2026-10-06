.RECIPEPREFIX = >
.PHONY: setup setup-voice run test eval bench context
setup:
> python -m pip install -e ".[dev]"
setup-voice:
> python -m pip install -e ".[dev,voice]"
> python -m scripts.download_models
run:
> python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
test:
> python -m pytest -q
eval:
> python -m scripts.eval
bench:
> python -m scripts.bench
context:
> python -m scripts.make_context
