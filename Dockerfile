# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Cloning the repository
RUN git clone https://github.com/YiZaha0/trash-manga-bot /app

WORKDIR /app

# Install pip requirements
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["bash", "start.sh"]
