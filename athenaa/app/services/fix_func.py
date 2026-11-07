with open(r'C:\Users\violi\Downloads\athena-discord-bot\athenaa\app\services\music_service.py', 'r') as f:
    content = f.read()

# Fix the function - it's missing body
old = 'def get_verified_radios() -> List[Dict[str, str]]:\n\n\n# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)\nCURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = ['

new = 'def get_verified_radios() -> List[Dict[str, str]]:\n    """Mengembalikan daftar stasiun radio internet terverifikasi dari config YAML."""\n    return VERIFIED_RADIO_STATIONS\n\n\n# Katalog 30 Lagu Satuan Populer (Tanpa Fake Video ID agar saat diputar selalu mencari stream aslinya)\nCURATED_YOUTUBE_SPOTIFY_CATALOG: List[Dict[str, Any]] = ['

if old in content:
    content = content.replace(old, new)
    with open(r'C:\Users\violi\Downloads\athena-discord-bot\athenaa\app\services\music_service.py', 'w') as f:
        f.write(content)
    print('SUCCESS: Fixed get_verified_radios function')
else:
    print('NOT FOUND: Pattern not matched')