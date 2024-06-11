postgres:
	docker run -ePOSTGRES_PASSWORD=password -p5432:5432 postgres

migrate:
	alembic upgrade head

redis:
	docker run --env-file .env -p6379:6379 redis redis-server --save "" --appendonly no

run-debug:
	export GRPC_VERBOSITY=debug && export GRPC_TRACE=all,-timer,-timer_check && python -m app.main

run:
	python -m app.main

build-grpc:
	 python -m grpc_tools.protoc -I=./ --python_out=./ --grpc_python_out=./  ./proto/*.proto

black:
	black -l50 .

docker:
	docker build -t smbrine/tm-density-calculator-grpc:v1.2.1 .
	docker push smbrine/tm-density-calculator-grpc:v1.2.1