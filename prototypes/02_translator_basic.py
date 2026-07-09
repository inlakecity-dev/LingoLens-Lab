from deep_translator import GoogleTranslator

print("Translation Tool")
print("1. English to Hindi")
print("2. Hindi to English")

choice = input("Choose option (1 or 2): ")

text = input("Enter text: ")

if choice == "1":
    translated = GoogleTranslator(
        source='en',
        target='hi'
    ).translate(text)

elif choice == "2":
    translated = GoogleTranslator(
        source='hi',
        target='en'
    ).translate(text)

else:
    print("Invalid choice")
    exit()

print("\nTranslated Text:")
print(translated)