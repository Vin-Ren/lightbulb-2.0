# Lightbulb 2.0
Lightbulb revamped using pycord. Adds support for slash commands.

Current Features:
- Music Player

More features to be added.


---
### Setup And Usage
1. Go to ffmpeg and download the binary suited for your OS. Add its location to the environment PATH variable or place it inside the top-level of this project.

2. Install all required dependencies.
```bash
$ python3 -m pip install -r requirements.txt
```

3. Create a dotenv file.
```bash
$ touch .env
```

4. Insert your bot token into the dotenv file.
```bash
$ echo "TOKEN=YOUR TOKEN HERE" > .env
```

5. Run the bot
```bash
$ python3 main.py
```
