import pandas as pd

try:
    # 1. อ่านไฟล์ CSV ของคุณ
    df = pd.read_csv('golden_dataset_sample.csv')

    # 2. สร้างเงื่อนไขเพื่อคัดกรองข้อมูล (แก้ไขชื่อคอลัมน์)
    #    - เงื่อนไขที่ 1: ข้อมูลจาก Spotify ต้องมี (เช็คจากคอลัมน์ 'track_name' ไม่เป็นค่าว่าง)
    #    - เงื่อนไขที่ 2: ข้อมูลจาก MusicBrainz/AcousticBrainz ยังไม่มี (เช็คจากคอลัมน์ 'mbid' เป็นค่าว่าง)
    songs_to_process = df[df['track_name'].notna() & df['mbid'].isna()]

    # 3. นับจำนวนและแสดงผลลัพธ์
    count = len(songs_to_process)

    if count > 0:
        print(f"✅ พบเพลงที่ต้องดึงข้อมูลจาก AcousticBrainz เพิ่มเติมทั้งหมด: {count} เพลง")
        print("\n--- ตัวอย่าง 5 เพลงแรกที่เข้าเงื่อนไข ---")
        print(songs_to_process[['track_name', 'artist_name', 'mbid']].head())
        
        # หากต้องการ save รายชื่อเพลงกลุ่มนี้เป็นไฟล์ใหม่ ให้ลบเครื่องหมาย # ข้างหน้าบรรทัดถัดไป
        # songs_to_process.to_csv('songs_for_acousticbrainz.csv', index=False)
        # print("\n✅ ได้บันทึกรายชื่อเพลงที่ต้องทำต่อเป็นไฟล์ 'songs_for_acousticbrainz.csv' แล้ว")

    else:
        print("✅ ไม่พบเพลงที่เข้าเงื่อนไข (ทุกเพลงได้รับการประมวลผลครบถ้วนแล้ว)")

except FileNotFoundError:
    print("❌ Error: ไม่พบไฟล์ 'golden_dataset_sample.csv' กรุณาตรวจสอบว่าไฟล์อยู่ในโฟลเดอร์เดียวกัน")
except KeyError as e:
    print(f"❌ Error: ไม่พบคอลัมน์ที่ต้องการในไฟล์ CSV. อาจจะไม่มีคอลัมน์ชื่อ {e}")
    print("👉 รายชื่อคอลัมน์ทั้งหมดในไฟล์ของคุณ:", df.columns.tolist())