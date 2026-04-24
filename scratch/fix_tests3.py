import os
import re

def fix_files():
    for root, dirs, files in os.walk("tests"):
        for file in files:
            if not file.endswith(".py"): continue
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            def repl(match):
                block = match.group(0)
                if 'seller_address=' not in block:
                    return block.replace('seller_name=', 'seller_address="123 Missing St", seller_name=')
                return block
                
            # Match InvoiceItem or InvoiceLineItem with up to 1 level of nested parentheses
            new_content = re.sub(r'(Invoice(?:Line)?Item\((?:[^()]+|\([^)]+\))+\))', repl, content, flags=re.DOTALL)
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Fixed {filepath}")

if __name__ == "__main__":
    fix_files()
