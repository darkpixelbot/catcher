# Use an official lightweight Python image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy only the necessary files (requirements first to optimize caching)
COPY requirements.txt .

# Install required Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Run the bot
CMD ["python", "main.py"]
