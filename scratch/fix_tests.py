import os
import re

TESTS_DIR = "tests"

def fix_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith(".py"): continue
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple approach: find InvoiceItem/InvoiceLineItem instantiations
            # and inject seller_address if missing.
            
            def repl_func(match):
                block = match.group(0)
                if "seller_address=" not in block:
                    return block.replace('seller_name=', 'seller_address="123 Missing St",\n        seller_name=')
                return block
                
            new_content = re.sub(r'InvoiceItem\([^)]+\)', repl_func, content)
            new_content = re.sub(r'InvoiceLineItem\([^)]+\)', repl_func, new_content)
            
            # test_sqlite_repo_line_items.py has InvoiceLineItem with many params, 
            # might not match [^)]+ if there are inner parens or complex args, but here it's usually simple.
            
            if new_content != content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Fixed {filepath}")

if __name__ == "__main__":
    fix_files(TESTS_DIR)
