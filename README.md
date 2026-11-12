# iSERM

iSERM is an experimental intelligent decision-support system for environmental risk management. The repository combines a Python desktop application with an Arduino sensor sketch and papers describing the work.

## Components

- `main.py`: PyQt desktop application, database handling, sensor-data processing, visualization, and prediction integrations.
- `serm.py`: generated Qt user-interface code.
- `SERM.ino`: Arduino sketch for collecting environmental sensor readings.
- The PDF documents provide research context and background.

The Python application references SQLite, MQTT, H2O, pandas, NumPy, SciPy, statsmodels, matplotlib, seaborn, scikit-fuzzy, APScheduler, and PyQt4. The Arduino sketch uses OneWire, DallasTemperature, and SoftwareSerial.

## Getting started

This is a legacy research prototype: no dependency lockfile or complete environment setup is supplied. Inspect the source for external services, local paths, sensor configuration, and credentials before running it. Reproducing the original environment may require older versions of Python libraries and a separately installed PyQt4.

Once an appropriate environment and the required services are configured, the desktop entry point is:

```sh
python main.py
```

The sensor sketch requires compatible hardware and its Arduino libraries. Review the pin definitions and calibration values before uploading it. Use simulated or non-sensitive data when experimenting.

## Limitations

The prototype has not been documented as a production monitoring or safety system. External APIs and legacy dependencies may no longer be available; validate measurements, models, and integrations independently before relying on results.
