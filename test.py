import http.client
import gzip
import io

conn = http.client.HTTPSConnection("gmgn.ai")
payload = ''
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Referer': 'https://gmgn.ai/meme?chain=sol',
    'Alt-Used': 'gmgn.ai',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'If-None-Match': 'W/a414-l8/w3z1JNxalxPb2NpnpiXw5qjM',
    'TE': 'trailers',
    'Cookie': '__cf_bm=u.GG9.i1txcmfQDRJnwSSNxlphSjZb1gueXN7_93fXg-1723873345-1.0.1.1-dw8di5yQ..ylr5mdT74RWp4gPqZ8fS23ewrAqxBxt_jr5QlsFDk0J84yXgc6x9OxdMGtb8fCIfcI90d37LwshQ'
}
conn.request("GET", "/defi/quotation/v1/rank/sol/pump/1h?limit=100&orderby=created_timestamp&direction=desc&new_creation=true&max_marketcap=9000&max_created=10m", payload, headers)
res = conn.getresponse()
data = res.read()

# Decompress the gzip data
decompressed_data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()

# Convert bytes to string (assuming the data is UTF-8 encoded)
decoded_data = decompressed_data.decode('utf-8')

print(decoded_data)
