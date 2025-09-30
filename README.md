Rasa voice-order bot (Vietnamese) - packaged for integration with WinForms app.

Instructions:
1. Install Python env and dependencies:
   pip install rasa rasa-sdk pyodbc

2. Place this folder as a rasa project. Train:
   rasa train

3. Run action server:
   rasa run actions --actions actions --debug

4. Run rasa server (in another terminal):
   rasa run --enable-api

5. Use RasaClient.cs in your WinForms app to send recognized text and parse JSON responses.
