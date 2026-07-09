from deep_translator import GoogleTranslator
from datetime import datetime

history = []

while True:

    print("\n===== Translation Tool =====")
    print("1. Auto Detect → Hindi")
    print("2. Auto Detect → English")
    print("3. Auto Detect → Japanese")
    print("4. Auto Detect → Chinese")
    print("5. Show History")
    print("6. Save History")
    print("7. Exit")

    choice = input("\nChoose option: ")

    if choice == "7":
        print("Goodbye!")
        break

    elif choice == "5":

        if len(history) == 0:
            print("\nNo history available.")

        else:
            print("\n===== Translation History =====")

            for item in history:
                print(item)

        continue

    elif choice == "6":

          timestamp = datetime.now().strftime("%m%d%yT%H%M%S")

          filename = f"THD{timestamp}.txt"

          with open(filename, "w", encoding="utf-8") as file:

               for item in history:
                   file.write(item + "\n")

          print(f"\nHistory saved to {filename}")

          continue

    text = input("\nEnter text: ")

    if choice == "1":

        translated = GoogleTranslator(
            source='auto',
            target='hi'
        ).translate(text)

    elif choice == "2":

        translated = GoogleTranslator(
            source='auto',
            target='en'
        ).translate(text)

    elif choice == "3":

        translated = GoogleTranslator(
            source='auto',
            target='ja'
        ).translate(text)

    elif choice == "4":

        translated = GoogleTranslator(
            source='auto',
            target='zh-CN'
        ).translate(text)
        
    else:
        print("Invalid choice")
        continue

    print("\nTranslated Text:")
    print(translated)

    history_entry = (
        f"Original: {text} | "
        f"Translated: {translated}"
    )

    history.append(history_entry)