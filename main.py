import socket
import sys
import threading
import time
import os
import datetime
import select
import json
import magic


class HTTPProtocol:
    methods = ["GET", "HEAD"]
    server_version = "HTTP/1.1"
    status_sentences = {200: "200 OK", 206: "206 Partial Content", 400: "400 Bad Request", 404: "404 Not Found",
                        405: "405 Method Not Allowed", 416: "416 Requested Range Not Satisfiable",
                        501: "501 Not Implemented", 505: "505 HTTP Version Not Supported"}

    def __init__(self, request_array, connection_socket, aux_info, server_data):
        self.document_root = ""
        self.connection_socket = connection_socket
        self.method = self.path = self.version = self.response_body = self.status = self.file_path = \
            self.end_byte = self.start_byte = None
        self.request_headers = {}
        self.response_headers = {}
        self.aux_info = aux_info
        self.server_data = server_data
        self.parse(request_array)

    def parse(self, request_array):
        self.response_headers["date"] = time.strftime("%c")
        self.response_headers["Accept-Ranges"] = "bytes"
        self.response_headers["Server"] = "gay-boi"
        self.response_headers["etag"] = "biggie-cheese"
        self.status = 200
        # noinspection PyBroadException")
        try:
            for line in request_array[1:]:
                key, value = line.split(":", 1)
                self.request_headers[key.strip().lower()] = value.strip().lower()

            host = self.request_headers["host"].split(":")[0].lower()
            for server_d in data["server"]:
                if server_d["vhost"] == host:
                    if server_d["ip"] == self.server_data["ip"] and server_d["port"] == self.server_data["port"]:
                        self.document_root = server_d["documentroot"]
            if self.document_root == "":
                self.status = 404
                self.response_error()
                return
            self.method, self.path, self.version = request_array[0].split()
            if self.version != self.server_version:
                self.status = 505
                self.response_error()
                return
            if self.path == "/":
                self.path = "/index.html"
            self.path = self.path.replace("%20", " ")
            if self.method not in self.methods:
                self.status = 501
                self.response_error()
                return
            if "range" in self.request_headers:
                pre, end = self.request_headers["range"].split("=")
                if pre != "bytes":
                    raise Exception
                arr = end.split("-")
                self.start_byte = int(arr[0])
                self.end_byte = int(arr[1]) if arr[1] else ""
                self.status = 206
            if "connection" in self.request_headers:
                val = self.request_headers["connection"]
                if val == "close":
                    self.aux_info["keep_alive"] = False
                else:
                    self.response_headers["Keep-Alive"] = "timeout=5, max=1000"
                    self.response_headers["Connection"] = "keep-alive"
            self.execute()

        except Exception as e:
            print("Erroring", e)
            self.status = 400
            self.response_error()
            return

    def execute(self):
        # noinspection PyBroadException
        try:
            if self.method in ["GET", "HEAD"]:
                self.file_path = self.document_root + self.path
                if not os.path.isfile(self.file_path):
                    self.status = 404
                    self.response_error()
                    return
                self.response_headers["Content-Type"] = magic.from_file(self.file_path, mime=True)
                file_size = os.path.getsize(self.file_path)
                if self.start_byte is not None:
                    if self.start_byte >= file_size or self.start_byte < 0:
                        self.status = 416
                        self.response_error()
                        return
                    if self.end_byte:
                        if self.end_byte < self.start_byte or self.end_byte >= file_size:
                            self.status = 416
                            self.response_error()
                            return
                        self.response_headers["Content-Length"] = self.end_byte - self.start_byte + 1
                        self.response_headers["Content-Range"] = "bytes {}-{}/{}".format(self.start_byte, self.end_byte,
                                                                                         file_size)
                    else:
                        self.response_headers["Content-Length"] = file_size - self.start_byte
                        self.response_headers["Content-Range"] = "bytes {}-{}/{}".format(self.start_byte, file_size - 1,
                                                                                         file_size)
                else:
                    self.response_headers["Content-Length"] = os.path.getsize(self.file_path)
                self.response_ok()
        except Exception as e:
            print(e)

    def response_ok(self):
        # noinspection PyBroadException
        try:
            self.connection_socket.send("{} {}\n".format(self.server_version, self.status_sentences[self.status]).encode())
            for key, value in self.response_headers.items():
                self.connection_socket.send("{}: {}\n".format(key, value).encode())
            self.connection_socket.send(b"\n")
            if self.method == "GET":
                with open(self.file_path, "rb") as f:
                    if self.start_byte is not None:
                        self.connection_socket.sendfile(f, self.start_byte, self.response_headers["Content-Length"])
                    else:
                        self.connection_socket.sendfile(f, 0, self.response_headers["Content-Length"])
        except Exception as e:
            print("Error ok", e)

    def response_error(self):
        self.connection_socket.send("{} {}\n".format(self.server_version, self.status_sentences[self.status]).encode())
        for key, value in self.response_headers.items():
            self.connection_socket.send("{}: {}\n".format(key, value).encode())
        self.connection_socket.send(b"\n")
        if self.status == 404:
            self.connection_socket.send(b"REQUESTED DOMAIN NOT FOUND")


def socket_worker(server_data, connection_socket, addr):
    start_time = datetime.datetime.now()
    aux_info = {"keep_alive": True}
    while True:
        data = None
        ready = select.select([connection_socket], [], [], 5)
        if ready[0]:
            data = connection_socket.recv(1024).decode('UTF-8')
            if data == "":
                break
        else:
            break
        data_array = []
        for line in data.splitlines():
            if not line:
                break
            data_array.append(line)

        HTTPProtocol(data_array, connection_socket, aux_info, server_data)
        if aux_info["keep_alive"]:
            start_time = datetime.datetime.now()
        elif not aux_info["keep_alive"] or (datetime.datetime.now() - start_time).seconds > 5:
            break
    connection_socket.close()


def start_server(server_data):
    server_address = (server_data["ip"], server_data["port"])
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(server_address)
    server_socket.listen(1024)
    print('Server starting on {} : {}'.format(*server_address))

    while 1:
        connection_socket, client_address = server_socket.accept()
        socket_thread = threading.Thread(target=socket_worker, args=(server_data, connection_socket, client_address))
        socket_thread.start()


threads = []
current_servers = []
config_path = sys.argv[1]
with open(config_path) as data_file:
    data = json.loads(data_file.read())
for server in data["server"]:
    if str(server["ip"]) + ":" + str(server["port"]) not in current_servers:
        current_servers.append(str(server["ip"]) + ":" + str(server["port"]))
        worker_thread = threading.Thread(target=start_server, args=(server,))
        threads.append(worker_thread)
        worker_thread.start()

for thread in threads:
    thread.join()








