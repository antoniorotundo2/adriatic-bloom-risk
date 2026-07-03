.PHONY: install run stop stop-clear ingest features train causal test

# Create the virtualenv and install the pipeline dependencies
install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

# Build and start the stack (PostGIS + API + web map)
run:
	docker compose up --build -d

# Stop the stack
stop:
	docker compose down

# Stop the stack and remove volumes and images
stop-clear:
	docker compose down -v --rmi all

# Download all public data, multi-year (Copernicus Marine, CDS, EWDS)
ingest:
	.venv/bin/python pipeline/ingest_satellite.py
	.venv/bin/python pipeline/ingest_sst.py
	.venv/bin/python pipeline/ingest_wind.py
	.venv/bin/python pipeline/ingest_po_discharge.py

# Build the feature table from the downloaded data
features:
	.venv/bin/python pipeline/features.py

# Train the model and write the predictions to PostGIS
train:
	.venv/bin/python pipeline/train_model.py

# Run the causal analysis (Step A: transparent, Step B: DoWhy)
causal:
	.venv/bin/python causal/a_transparent_estimate.py
	.venv/bin/python causal/b_dowhy_estimate.py

# Run the test suite
test:
	.venv/bin/python -m pytest tests/ -v
