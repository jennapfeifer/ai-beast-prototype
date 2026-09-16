import os
bind = "0.0.0.0:" + os.getenv("PORT", "5000")
workers = 1
threads = 8
timeout = 120
accesslog = "-"
