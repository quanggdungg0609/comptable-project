import os

TESTS_DIR = "tests"

def fix_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith(".py"): continue
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            parts = content.split('seller_name=')
            if len(parts) == 1:
                continue
                
            new_content = parts[0]
            for i in range(1, len(parts)):
                preceding = new_content[-300:]
                if 'seller_address=' not in preceding and 'seller_address =' not in preceding:
                    # we use the indentation of the preceding line
                    indent = preceding.split('\n')[-1]
                    new_content += f'seller_address="123 Missing St",\n{indent}seller_name=' + parts[i]
                else:
                    new_content += 'seller_name=' + parts[i]
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Fixed {filepath}")

if __name__ == "__main__":
    fix_files(TESTS_DIR)
