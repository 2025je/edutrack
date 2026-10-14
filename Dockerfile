# Usamos una imagen oficial de Python en su versión ligera
FROM python:3.11-slim

# Evita que Python escriba archivos .pyc en el disco
ENV PYTHONDONTWRITEBYTECODE=1
# Evita que Python guarde en el búfer los flujos de salida (útil para ver logs en tiempo real)
ENV PYTHONUNBUFFERED=1

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia e instala las dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código del proyecto al contenedor
COPY . /app/