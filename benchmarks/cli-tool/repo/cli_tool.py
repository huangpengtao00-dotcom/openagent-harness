import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv:
        print("usage: cli-tool [--help]")
        return 0
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
