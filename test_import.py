import sys
print("sys.path:", sys.path)
try:
    import voice_journal
    print("Imported voice_journal")
    print(voice_journal.__file__)
except Exception as e:
    print("Error:", e)
