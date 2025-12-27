# connection_manager.py

import asyncio
from typing import Dict
import logging
from services.telnet import TelnetClient

# Import TelnetClient Anda di sini
# from your_script import TelnetClient 

class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, TelnetClient] = {}
        # Jangan buat lock/task di sini!

    async def get_connection(self, host, username, password, is_c600) -> TelnetClient:
        # Cek apakah sudah ada koneksi tersimpan
        if host in self._connections:
            client = self._connections[host]
            # Cek apakah fisik koneksinya masih hidup
            if client.writer and not client.writer.is_closing():
                return client
            else:
                # Kalau sudah mati, hapus dari memori
                del self._connections[host]

        # Buat object baru
        logging.info(f"✨ Membuat session object baru untuk {host}")
        client = TelnetClient(host, username, password, is_c600)
        
        # Konek (Lock akan dibuat otomatis di dalam sini karena property lazy load)
        await client.connect()
        
        # Simpan ke dictionary global
        self._connections[host] = client
        
        # Jalankan Keepalive di background (Fire and Forget)
        asyncio.create_task(self._keepalive_worker(client))
        
        return client

    async def _keepalive_worker(self, client: TelnetClient):
            """
            Mengirim Enter setiap 60 detik agar tidak ditendang OLT.
            VERSI FIX: Tidak melakukan read() agar tidak bentrok dengan main thread.
            """
            try:
                while True:
                    await asyncio.sleep(60)
                    
                    # 1. Cek jika koneksi sudah mati/diclose manual, hentikan worker
                    if not client.writer or client.writer.is_closing():
                        break

                    # 2. Cek idle time (apakah user aktif dalam 50 detik terakhir?)
                    now = asyncio.get_event_loop().time()
                    if now - client.last_activity > 50:
                        
                        # Gunakan Lock agar tidak menulis saat command lain sedang jalan
                        if client.lock.locked():
                            # Jika sedang ada command jalan, kita tidak perlu kirim keepalive
                            # karena aktivitas itu sendiri sudah mereset timer OLT.
                            continue

                        async with client.lock:
                            if client.writer and not client.writer.is_closing():
                                try:
                                    # Cukup kirim ENTER saja untuk reset timer OLT
                                    client.writer.write("\n")
                                    await client.writer.drain()
                                    
                                    # --- HAPUS BAGIAN READ DI SINI ---
                                    # await client.reader.read(...) <--- INI PENYEBAB CRASH
                                    # Kita tidak peduli balasan dari keepalive.
                                    
                                    # Update last activity agar loop berikutnya menunggu 60 detik lagi
                                    client.last_activity = asyncio.get_event_loop().time()
                                    
                                except Exception as e:
                                    logging.warning(f"Gagal kirim keepalive: {e}")
                                    break
            except Exception as e:
                logging.error(f"Keepalive Worker Crash pada {client.host}: {e}")

# Global Instance
olt_manager = ConnectionManager()