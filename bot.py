import requests
import hmac
import hashlib
import time
import urllib.parse

api_key = ""
api_secret= ""
endpoint="https://testnet.binancefuture.com/fapi/v2/account"
timestamp = round(time.time()*1000)
params = {
    "timestamp": timestamp
}
querystring = urllib.parse.urlencode(params)
signature = hmac.new(api_secret.encode('utf-8'), msg=querystring.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
url = f'{endpoint}?{querystring}&signature={signature}'
headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-MBX-APIKEY': api_key

}
response = requests.get(url, headers=headers)
print(response.request.headers)
print(response.url)
print(response.text)


