from tools.files import list_files

print("1. Thư mục hợp lệ")
print(list_files.invoke({"path": "data/policies"}))

print("\n2. Đường dẫn file")
print(list_files.invoke({"path": "data/policies/abc.md"}))

print("\n3. Không tồn tại")
print(list_files.invoke({"path": "data/not-exist"}))

print("\n4. Vượt workspace")
print(list_files.invoke({"path": "../"}))