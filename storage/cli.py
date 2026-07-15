import sys
import json
from store import create_company, delete_company, list_companies, list_files, delete_file

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No command provided"}))
        return

    command = sys.argv[1]

    try:
        if command == "create_company":
            name = sys.argv[2]
            success = create_company(name)
            print(json.dumps({"success": success, "company": name}))

        elif command == "delete_company":
            name = sys.argv[2]
            success = delete_company(name)
            print(json.dumps({"success": success, "company": name}))

        elif command == "list_companies":
            companies = list_companies()
            print(json.dumps({"companies": companies}))

        elif command == "list_files":
            company = sys.argv[2]
            files = list_files(company)
            print(json.dumps({"company": company, "files": files}))

        elif command == "delete_file":
            company = sys.argv[2]
            filename = sys.argv[3]
            success = delete_file(company, filename)
            print(json.dumps({"success": success, "company": company, "file": filename}))

        else:
            print(json.dumps({"error": f"Unknown command: {command}"}))

    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()
