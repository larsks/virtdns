FROM python:3.9

RUN pip install -U pip
RUN pip install pipenv
WORKDIR /app
COPY Pipfile /app/Pipfile
RUN pipenv install
COPY . /app

ENTRYPOINT ["pipenv", "run", "python", "-m", "virtdns"]
