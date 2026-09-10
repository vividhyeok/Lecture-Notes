"""Lecture Notes server entry point with convenience-safe defaults."""
import server
from convenience import ConvenienceLibrary

server.Library = ConvenienceLibrary

if __name__ == '__main__':
    server.main()
