from backend.grottocenter_api.grottocenter import Grottocenter

if __name__ == "__main__":
    gc = Grottocenter()
    result = gc.health_check()
    print(result)
