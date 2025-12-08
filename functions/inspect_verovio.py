import verovio
import json

tk = verovio.toolkit()
# Try to get available options. 
# Based on some verovio versions, getAvailableOptions() might return a json string of all options.
try:
    options = tk.getAvailableOptions()
    print(options)
except Exception as e:
    print(f"Error getting options: {e}")
