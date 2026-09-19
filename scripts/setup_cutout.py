"""Download fixed rembg U2Net weights once; never uploads user images."""

import hashlib

import httpx

from studio.config import data_dir


def main():
    target = data_dir() / "models" / "u2net.onnx"
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = "60024c5c889badc19c04ad937298a77b"
    if target.is_file() and hashlib.md5(target.read_bytes()).hexdigest() == expected:
        print("本地抠图模型已就绪")
        return
    temp = target.with_suffix(".download")
    digest = hashlib.md5()
    try:
        with httpx.stream(
            "GET",
            "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
            follow_redirects=True,
            timeout=60,
        ) as response:
            response.raise_for_status()
            with temp.open("wb") as file:
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > 200 * 1024 * 1024:
                        raise ValueError("下载超出预期大小")
                    digest.update(chunk)
                    file.write(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("模型校验失败")
        temp.replace(target)
        print("本地 U2Net 模型已安装，校验通过")
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
