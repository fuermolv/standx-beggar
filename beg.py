from calendar import c
import json
import uuid
import time
import base64
import requests
from nacl.signing import SigningKey
import math

BASE_URL = "https://perps.standx.com"
PAIR = "BTC-USD"
POSITION = 50000
BPS = 20
MIN_BPS = 10
MAX_BPS = 30
SIDE = "sell"



def get_headers(auth, payload_str=None):
    x_request_version = "v1"
    x_request_id = str(uuid.uuid4()) 
    x_request_timestamp = str(int(time.time() * 1000))
    access_token = auth['access_token']
    signing_key = auth['signing_key']
    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-request-sign-version": x_request_version,
        "x-request-id": x_request_id,
        "x-request-timestamp": x_request_timestamp,
    }
    if payload_str:
        msg = f"{x_request_version},{x_request_id},{x_request_timestamp},{payload_str}"
        msg_bytes = msg.encode("utf-8")
        signed = signing_key.sign(msg_bytes)
        signature = base64.b64encode(signed.signature).decode("ascii")
        headers["x-request-signature"] = signature
        headers["Content-Type"] = "application/json"
    return headers



# https://docs.standx.com/standx-api/perps-http#query-symbol-price
def get_price(auth):
    url = f"{BASE_URL}/api/query_symbol_price"
    params = {"symbol": PAIR}
    resp = requests.get(url, headers=get_headers(auth), params=params)
    if resp.status_code != 200:
        raise Exception(f"get_price failed: {resp.status_code} {resp.text}")
    return resp.json()


# https://docs.standx.com/standx-api/perps-http#create-new-order
def create_order(auth, price, qty):
    url = f"{BASE_URL}/api/new_order"
    cl_ord_id = str(uuid.uuid4())
    data = {
        "symbol": PAIR,
        "side": SIDE,
        "order_type": "limit",
        "qty": qty,
        "price": str(price),
        'margin_mode':  "cross",
        "time_in_force": "gtc",
        "reduce_only": False,
        "cl_ord_id": cl_ord_id,
    }
    
    payload_str = json.dumps(data, separators=(",", ":"))
    resp = requests.post(url, headers=get_headers(auth, payload_str), data=payload_str)
    if resp.status_code != 200:
        raise Exception(f"create_order failed: {resp.status_code} {resp.text} data: {data}")
    print(f'creating order: side={SIDE}, price={price}, qty={qty}, cl_ord_id={cl_ord_id}')
    return cl_ord_id



def maker_clean_position(auth, price, qty):
    url = f"{BASE_URL}/api/new_order"
    cl_ord_id = str(uuid.uuid4())
    if SIDE == "buy":
        side = "sell"
    else:
        side = "buy"
    data = {
        "symbol": PAIR,
        "side": side,
        "order_type": "limit",
        "qty": qty,
        "price": str(price),
        'margin_mode':  "cross",
        "time_in_force": "gtc",
        "reduce_only": True,
        "cl_ord_id": cl_ord_id,
    }
    
    payload_str = json.dumps(data, separators=(",", ":"))
    resp = requests.post(url, headers=get_headers(auth, payload_str), data=payload_str)
    if resp.status_code != 200:
        raise Exception(f"create_order failed: {resp.status_code} {resp.text}")
    print(f'maker cleaning position with limit order: side={side}, price={price}, qty={qty}')
    return cl_ord_id


def taker_clean_position(auth, qty):
    url = f"{BASE_URL}/api/new_order"
    if SIDE == "buy":
        side = "sell"
    else:
        side = "buy"
    data = {
        "symbol": PAIR,
        "side": side,
        "order_type": "market",
        "qty": qty,
        'margin_mode':  "cross",
        "time_in_force": "gtc",
        "reduce_only": True,
    }
    payload_str = json.dumps(data, separators=(",", ":"))
    resp = requests.post(url, headers=get_headers(auth, payload_str), data=payload_str)
    if resp.status_code != 200:
        raise Exception(f"create_order failed: {resp.status_code} {resp.text}") 
    print(f'cleaning position with taker: side={side}, qty={qty}')
    return resp.json()



# https://docs.standx.com/standx-api/perps-http#cancel-multiple-orders
def cancel_order(auth, cl_order_id):
    url = f"{BASE_URL}/api/cancel_orders"
    data = {
        "cl_ord_id_list": [cl_order_id],
    }
    payload_str = json.dumps(data, separators=(",", ":"))
    resp = requests.post(url, headers=get_headers(auth, payload_str), data=payload_str)
    if resp.status_code != 200:
        raise Exception(f"cancel_orders failed: {resp.status_code} {resp.text}")
    print(f'cancel order: {cl_order_id}')
    return resp.json()




# https://docs.standx.com/standx-api/perps-http#query-order
def query_order(auth, cl_ord_id):
    url = f"{BASE_URL}/api/query_order"
    params = {"cl_ord_id": cl_ord_id}
    resp = requests.get(url, headers=get_headers(auth), params=params)
    if resp.status_code != 200:
        raise Exception(f"query_open_orders failed: {resp.status_code} {resp.text}")
    return resp.json()


def clean_position(auth, qty, price):
    cl_ord_id = maker_clean_position(auth, price, qty)
    try:
        for index in range(120):
            order = query_order(auth, cl_ord_id)
            print(f'{index} waiting maker cleaning position order status: {order["status"]} qty: {order["qty"]} price: {price}, order price: {order["price"]}')
            if order["status"] == "filled":
                return
            time.sleep(1)
    except Exception as e:
        print("maker clean position exception, using taker to clean position")
        taker_clean_position(auth, qty)
        raise e
    print("maker clean position timeout, canceling order")
    cancel_order(auth, cl_ord_id)
    print("using taker to clean position")
    taker_clean_position(auth, qty)


def main():
    with open("standx_beggar_auth.json", "r") as f:
        auth_json = json.load(f)
        auth = {
            'access_token': auth_json['access_token'],
            'signing_key': SigningKey(bytes.fromhex(auth_json['signing_key'])),
        }
    cl_ord_id = None
    try:
        while True:
            index_price = float(get_price(auth)["index_price"])
            if cl_ord_id:
                order = query_order(auth, cl_ord_id)
                diff_bps = abs(index_price - float(order["price"])) / index_price * 10000
                print(f'order qty: {order["qty"]} status: {order["status"]}, index price: {index_price}, order price: {order["price"]},  diff_bps: {diff_bps}')
                if order["status"] == "filled":
                    clean_position(auth, float(order["qty"]), float(order["price"]))
                    cl_ord_id = None
                    print("position cleaned, placing new order after 10 minutes")
                    time.sleep(1)
                    time.sleep(600)
                if diff_bps <= MIN_BPS or diff_bps >= MAX_BPS:
                    cancel_order(auth, cl_ord_id)
                    cl_ord_id = None
            else:
                sign = 1 if SIDE == "sell" else -1
                order_price = index_price * (1 + sign * BPS / 10000)
                order_price = format(order_price, ".2f")
                qty = POSITION / float(order_price)
                qty = format(qty, ".4f")
                cl_ord_id = create_order(auth, order_price, qty)
            time.sleep(0.1)
    finally:
        if cl_ord_id:
            print("cleaning up open order")
            cancel_order(auth, cl_ord_id)



if __name__ == "__main__":
    main()
