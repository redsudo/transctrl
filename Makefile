.PHONY: proto clean test build-image test-integration

PYTHON=uv run python
PIP=uv pip
GRPC_TOOLS_PYTHON_PROTOC=uv run python -m grpc_tools.protoc

proto:
	$(GRPC_TOOLS_PYTHON_PROTOC) -I./proto --python_out=./src --grpc_python_out=./src ./proto/transctrl.proto

clean:
	rm -f src/*_pb2.py src/*_pb2_grpc.py

test:
	PYTHONPATH=. uv run pytest tests/ -v --ignore=tests/integration

build-image:
	docker build -t transctrl:latest .

test-integration:
	docker build -f Dockerfile.test -t transctrl-test .
	docker run --privileged --rm transctrl-test

