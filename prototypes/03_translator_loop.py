from deep_translator import GoogleTranslator

while True:

    print("\nTranslation Tool")
    print("1. English to Hindi")
    print("2. Hindi to English")
    print("3. Exit")

    choice = input("Choose option: ")

    if choice == "3":
        print("Goodbye!")
        break

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
        continue

    print("\nTranslated Text:")
    print(translated)