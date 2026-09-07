import inspect, json, sys, pathlib
import xai_compress.compression as comp
import xai_compress.cli as cli
from xai_compress.hybrid.selector import HybridSelector

def main():
    data = {
        "compress_file": str(inspect.signature(comp.compress_file)),
        "decompress_file": str(inspect.signature(comp.decompress_file)),
        "HybridSelector_init": str(inspect.signature(HybridSelector.__init__)),
        "cli_main": str(inspect.signature(cli.main)),
    }
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
