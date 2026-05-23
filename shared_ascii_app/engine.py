from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import itertools
import math
import secrets
import sys
import time

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont
from reportlab.pdfgen import canvas

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(1_000_000)

try:
    from PIL import ImageResampling as _ImageResampling
    RESAMPLING_LANCZOS = _ImageResampling.LANCZOS
except Exception:
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS


ALPHABETS = {
    "numeric": "0123456789",
    "hexadecimal": "0123456789ABCDEF",
    "alphanumeric": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "alphabetical": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "keyboardsmash": "1234567890!@#$%^&*()qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM",
}
DEFAULT_ALPHABET = ALPHABETS["numeric"]

Logger = Callable[[str], None]


def _noop_logger(message: str) -> None:
    return None


@dataclass(slots=True)
class GenerationSettings:
    image_path: str
    output_dir: str
    sample_width: int = 80
    bold: bool = False
    background_color: str = "#ffffff"
    text_color: str = "#000000"
    grayscale_method: str = "standard"
    color_scheme: str = "grayscale (standard)"
    invert_colors: bool = False
    brightness_modifier: float = 1.0
    enforce_primality: bool = False
    highlight_deltas: bool = True
    save_pdf: bool = True
    save_jpg: bool = True
    save_txt: bool = True
    output_suffix: str = ""
    update_interval: int = 15
    top_bubble_pixels: int = 20
    max_bubble_flips: int = 5
    max_prime_checks: int = 250000
    small_prime_limit: int = 1000
    probable_prime_rounds: int = 25
    jpg_scale: int = 4
    preview_max_size: tuple[int, int] = (640, 480)


@dataclass(slots=True)
class GenerationResult:
    char_matrix: np.ndarray
    gray_matrix: np.ndarray
    source_image: Image.Image
    swapped_mask: np.ndarray
    preview_image: Image.Image
    output_paths: dict[str, str]
    output_base_name: str
    prime_requested: bool
    prime_found: bool
    checks: int = 0
    sieve_rejects: int = 0
    sample_size: tuple[int, int] = (0, 0)


def _parse_color(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)


def _apply_brightness_modifier(image: Image.Image, modifier: float) -> Image.Image:
    if modifier == 1.0:
        return image
    return ImageEnhance.Brightness(image).enhance(modifier)


def _invert_rgb_array(array: np.ndarray) -> np.ndarray:
    return (255 - array).clip(0, 255).astype(np.uint8)


def _color_matrix_from_source(image: Image.Image, scheme: str, invert: bool) -> np.ndarray | None:
    scheme_key = scheme.strip().lower()
    rgb_image = image.convert("RGB")
    rgb_array = np.asarray(rgb_image, dtype=np.uint8)

    if scheme_key in {"grayscale", "grayscale (standard)", "standard"}:
        gray = np.asarray(rgb_image.convert("L"), dtype=np.uint8)
        color_matrix = np.stack([gray, gray, gray], axis=-1)
    elif scheme_key == "full color":
        color_matrix = rgb_array
    elif scheme_key == "hue match":
        hsv_image = rgb_image.convert("HSV")
        hsv_array = np.asarray(hsv_image, dtype=np.uint8).copy()
        hsv_array[..., 1] = 255
        hsv_array[..., 2] = 255
        color_matrix = np.asarray(Image.fromarray(hsv_array, mode="HSV").convert("RGB"), dtype=np.uint8)
    elif scheme_key == "rgb only":
        palette = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.int16)
        flat = rgb_array.reshape(-1, 3).astype(np.int16)
        distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
        color_matrix = palette[distances.argmin(axis=1)].astype(np.uint8).reshape(rgb_array.shape)
    elif scheme_key == "rygcbm only":
        palette = np.array(
            [
                [255, 0, 0],
                [255, 255, 0],
                [0, 255, 0],
                [0, 255, 255],
                [0, 0, 255],
                [255, 0, 255],
            ],
            dtype=np.int16,
        )
        flat = rgb_array.reshape(-1, 3).astype(np.int16)
        distances = ((flat[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
        color_matrix = palette[distances.argmin(axis=1)].astype(np.uint8).reshape(rgb_array.shape)
    else:
        color_matrix = rgb_array

    if invert:
        color_matrix = _invert_rgb_array(color_matrix)

    return color_matrix


def _resolve_render_colors(settings: GenerationSettings, source_image: Image.Image) -> tuple[tuple[int, int, int], np.ndarray | None, tuple[int, int, int]]:
    background_rgb = _parse_color(settings.background_color)
    if settings.invert_colors:
        background_rgb = tuple(255 - value for value in background_rgb)
    color_matrix = _color_matrix_from_source(source_image, settings.color_scheme, settings.invert_colors)
    text_rgb = _parse_color(settings.text_color)
    if settings.invert_colors:
        text_rgb = tuple(255 - value for value in text_rgb)
    return background_rgb, color_matrix, text_rgb


def standard_grayscale(image: Image.Image) -> Image.Image:
    return image.convert("L")


def pca_grayscale(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float32) / 255.0
    height, width, _ = arr.shape
    pixels = arr.reshape(-1, 3)

    centered = pixels - pixels.mean(axis=0, keepdims=True)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    projection = centered @ vh[0]
    gray = projection.reshape(height, width)

    gray -= gray.min()
    gray /= gray.max() + 1e-8

    luminance = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    corr = np.corrcoef(gray.ravel(), luminance.ravel())[0, 1]
    if np.isnan(corr) or corr < 0:
        gray = 1.0 - gray

    out = (gray * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="L")


def load_gray_image(image: Image.Image, method: str, brightness_modifier: float) -> Image.Image:
    working = _apply_brightness_modifier(image, brightness_modifier)
    method_key = method.strip().lower()
    if method_key == "pca":
        return pca_grayscale(working)
    return standard_grayscale(working)


def get_brightness_values(alphabet: str) -> list[tuple[float, str]]:
    brightness_values: list[tuple[float, str]] = []
    for digit in alphabet:
        digit_image = Image.new("L", (10, 10), color=255)
        draw = ImageDraw.Draw(digit_image)
        draw.text((0, 0), str(digit), fill=0)
        total_brightness = 0
        for x in range(10):
            for y in range(10):
                total_brightness += digit_image.getpixel((x, y))
        avg_brightness = total_brightness / 100
        brightness_values.append((avg_brightness, digit))

    brightness_values.sort()
    min_brightness = brightness_values[0][0]
    max_brightness = brightness_values[-1][0]
    spread = max(max_brightness - min_brightness, 1e-8)
    return [((brightness - min_brightness) / spread, digit) for (brightness, digit) in brightness_values]


def get_char_matrix(
    sample_height: int,
    sample_width: int,
    gray_image: Image.Image,
    brightness_values: list[tuple[float, str]],
) -> tuple[np.ndarray, np.ndarray]:
    gray_array = np.asarray(gray_image, dtype=np.float32) / 255.0
    char_matrix = np.empty((sample_height, sample_width), dtype="<U1")

    digit_brightness = [(float(value), str(digit)) for value, digit in brightness_values]
    for y in range(sample_height):
        for x in range(sample_width):
            brightness = float(gray_array[y, x])
            closest_digit = digit_brightness[0][1]
            closest_diff = 2.0
            for value, digit in digit_brightness:
                diff = abs(value - brightness)
                if diff < closest_diff:
                    closest_diff = diff
                    closest_digit = digit
            char_matrix[y, x] = closest_digit

    return char_matrix, gray_array


def char_matrix_to_big_number(char_matrix: np.ndarray) -> int:
    flat_digits = "".join(char_matrix.reshape(-1).tolist())
    return int(flat_digits)


def big_number_to_char_matrix(big_number: int, width: int, height: int) -> np.ndarray:
    expected_digits = width * height
    digits = str(big_number).zfill(expected_digits)
    chars = np.array(list(digits), dtype="<U1")
    return chars.reshape((height, width))


def rank_bubble_pixels(
    char_matrix: np.ndarray,
    gray_matrix: np.ndarray,
    brightness_values: list[tuple[float, str]],
    top_n: int = 20,
    exclude_pos: tuple[int, int] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    digit_to_brightness = {str(digit): float(value) for (value, digit) in brightness_values}
    digits = list(digit_to_brightness.keys())
    candidates: list[dict[str, object]] = []

    for y in range(char_matrix.shape[0]):
        for x in range(char_matrix.shape[1]):
            if exclude_pos is not None and (y, x) == exclude_pos:
                continue

            current_digit = str(char_matrix[y, x])
            if current_digit not in digit_to_brightness:
                continue

            pixel_brightness = float(gray_matrix[y, x])
            current_diff = abs(pixel_brightness - digit_to_brightness[current_digit])
            best_alt = None
            best_alt_diff = None

            for digit in digits:
                if digit == current_digit:
                    continue
                alt_diff = abs(pixel_brightness - digit_to_brightness[digit])
                if best_alt_diff is None or alt_diff < best_alt_diff:
                    best_alt_diff = alt_diff
                    best_alt = digit

            if best_alt is None or best_alt_diff is None:
                continue

            penalty = best_alt_diff - current_diff
            candidates.append(
                {
                    "y": y,
                    "x": x,
                    "current": current_digit,
                    "alternative": best_alt,
                    "penalty": float(penalty),
                    "current_diff": float(current_diff),
                    "alt_diff": float(best_alt_diff),
                }
            )

    candidates.sort(key=lambda item: (item["penalty"], item["alt_diff"]))
    return candidates[:top_n], candidates


def _small_primes(limit: int = 1000) -> list[int]:
    sieve = [True] * (limit + 1)
    sieve[0] = False
    sieve[1] = False
    p = 2
    while p * p <= limit:
        if sieve[p]:
            for value in range(p * p, limit + 1, p):
                sieve[value] = False
        p += 1
    return [value for value in range(2, limit + 1) if sieve[value]]


def _probable_prime(number: int, rounds: int = 25) -> bool:
    if number < 2:
        return False

    small_primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]
    for prime in small_primes:
        if number == prime:
            return True
        if number % prime == 0:
            return False

    d = number - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    for _ in range(rounds):
        base = secrets.randbelow(number - 3) + 2
        x = pow(base, d, number)
        if x in (1, number - 1):
            continue

        for _ in range(s - 1):
            x = pow(x, 2, number)
            if x == number - 1:
                break
        else:
            return False

    return True


def find_prime_by_bubble_permutations(
    char_matrix: np.ndarray,
    gray_matrix: np.ndarray,
    brightness_values: list[tuple[float, str]],
    top_n: int = 20,
    max_flips: int = 5,
    max_checks: int = 250000,
    update_interval: int = 15,
    small_prime_limit: int = 1000,
    probable_prime_rounds: int = 25,
    logger: Logger | None = None,
) -> tuple[np.ndarray | None, dict[str, object]]:
    emit = logger or _noop_logger

    if char_matrix.size == 0:
        return None, {"checks": 0, "sieve_rejects": 0}

    digit_to_brightness = {str(digit): float(value) for (value, digit) in brightness_values}
    valid_endings = [digit for digit in ["1", "3", "7", "9"] if digit in digit_to_brightness]
    if not valid_endings:
        emit("No valid ending digits (1, 3, 7, 9) available in this alphabet.")
        return None, {"checks": 0, "sieve_rejects": 0}

    height, width = char_matrix.shape
    total_digits = height * width
    end_pos = (height - 1, width - 1)
    end_idx = total_digits - 1
    end_gray = float(gray_matrix[end_pos[0], end_pos[1]])

    top_candidates, all_candidates = rank_bubble_pixels(
        char_matrix,
        gray_matrix,
        brightness_values,
        top_n=top_n,
        exclude_pos=end_pos,
    )
    emit(f"Scored {len(all_candidates)} candidate pixels; using top {len(top_candidates)} bubble pixels.")

    flat_chars = char_matrix.reshape(-1).tolist()
    base_digits = [int(char) for char in flat_chars]
    base_digit_sum = sum(base_digits)
    base_number = char_matrix_to_big_number(char_matrix)
    pos_multiplier = [pow(10, total_digits - 1 - idx) for idx in range(total_digits)]

    ending_options = []
    for end_digit in valid_endings:
        end_penalty = abs(end_gray - digit_to_brightness[end_digit])
        end_old = base_digits[end_idx]
        end_new = int(end_digit)
        end_delta = (end_new - end_old) * pos_multiplier[end_idx]
        end_digit_sum_delta = end_new - end_old
        ending_options.append((end_digit, end_penalty, end_delta, end_digit_sum_delta))
    ending_options.sort(key=lambda item: item[1])

    prepared_candidates: list[dict[str, object]] = []
    for candidate in top_candidates:
        idx = int(candidate["y"]) * width + int(candidate["x"])
        old_digit = int(candidate["current"])
        new_digit = int(candidate["alternative"])
        prepared_candidates.append(
            {
                "idx": idx,
                "y": int(candidate["y"]),
                "x": int(candidate["x"]),
                "old_digit": old_digit,
                "new_digit": new_digit,
                "delta_n": (new_digit - old_digit) * pos_multiplier[idx],
                "delta_digit_sum": new_digit - old_digit,
                "penalty": float(candidate["penalty"]),
            }
        )

    small_primes = [prime for prime in _small_primes(small_prime_limit) if prime not in (2, 5)]

    t0 = time.time()
    last_update = -1
    checks = 0
    sieve_rejects = 0

    for end_digit, end_penalty, end_delta, end_digit_sum_delta in ending_options:
        n_end = base_number + end_delta
        digit_sum_end = base_digit_sum + end_digit_sum_delta
        checks += 1

        if digit_sum_end % 3 != 0:
            passed_small_prime_sieve = True
            for prime in small_primes:
                if n_end % prime == 0:
                    passed_small_prime_sieve = False
                    break
            if passed_small_prime_sieve and _probable_prime(n_end, rounds=probable_prime_rounds):
                elapsed = time.time() - t0
                prime_matrix = char_matrix.copy()
                prime_matrix[end_pos[0], end_pos[1]] = end_digit
                emit(f"✓ Found probable prime after {checks} checks in {elapsed:.2f} seconds.")
                return prime_matrix, {
                    "checks": checks,
                    "flips": 0,
                    "ending": end_digit,
                    "penalty": float(end_penalty),
                    "sieve_rejects": sieve_rejects,
                }
        else:
            sieve_rejects += 1

        for flips in range(1, max_flips + 1):
            if not prepared_candidates:
                break

            for combo in itertools.combinations(prepared_candidates, flips):
                if checks >= max_checks:
                    emit(f"Reached max_checks={max_checks} without finding a probable prime.")
                    return None, {"checks": checks, "sieve_rejects": sieve_rejects}

                checks += 1
                delta_n = end_delta
                delta_digit_sum = end_digit_sum_delta
                total_penalty = end_penalty
                for swap in combo:
                    delta_n += int(swap["delta_n"])
                    delta_digit_sum += int(swap["delta_digit_sum"])
                    total_penalty += float(swap["penalty"])

                candidate_number = base_number + delta_n
                candidate_digit_sum = base_digit_sum + delta_digit_sum

                if candidate_digit_sum % 3 == 0:
                    sieve_rejects += 1
                    continue

                passed_small_prime_sieve = True
                for prime in small_primes:
                    if candidate_number % prime == 0:
                        passed_small_prime_sieve = False
                        break
                if not passed_small_prime_sieve:
                    sieve_rejects += 1
                    continue

                if _probable_prime(candidate_number, rounds=probable_prime_rounds):
                    elapsed = time.time() - t0
                    prime_matrix = char_matrix.copy()
                    prime_matrix[end_pos[0], end_pos[1]] = end_digit
                    for swap in combo:
                        prime_matrix[int(swap["y"]), int(swap["x"])] = str(swap["new_digit"])
                    emit(f"✓ Found probable prime after {checks} checks in {elapsed:.2f} seconds.")
                    return prime_matrix, {
                        "checks": checks,
                        "flips": flips,
                        "ending": end_digit,
                        "penalty": float(total_penalty),
                        "sieve_rejects": sieve_rejects,
                    }

                elapsed_int = int(time.time() - t0)
                if update_interval > 0 and elapsed_int > 0 and elapsed_int % update_interval == 0 and elapsed_int != last_update:
                    last_update = elapsed_int
                    emit(
                        f"Checked {checks} candidates in {elapsed_int} seconds; "
                        f"sieve rejected {sieve_rejects} so far."
                    )

    return None, {"checks": checks, "sieve_rejects": sieve_rejects}


def enforce_primality(
    char_matrix: np.ndarray,
    gray_matrix: np.ndarray,
    brightness_values: list[tuple[float, str]],
    top_n: int = 20,
    max_flips: int = 5,
    max_checks: int = 250000,
    update_interval: int = 15,
    small_prime_limit: int = 1000,
    probable_prime_rounds: int = 25,
    logger: Logger | None = None,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    emit = logger or _noop_logger
    num_digits = char_matrix.size

    emit(f"Original number has {num_digits} digits.")
    emit("Searching for probable prime via bubble-pixel permutations...")

    prime_char_matrix, meta = find_prime_by_bubble_permutations(
        char_matrix=char_matrix,
        gray_matrix=gray_matrix,
        brightness_values=brightness_values,
        top_n=top_n,
        max_flips=max_flips,
        max_checks=max_checks,
        update_interval=update_interval,
        small_prime_limit=small_prime_limit,
        probable_prime_rounds=probable_prime_rounds,
        logger=logger,
    )

    if prime_char_matrix is None:
        emit("Could not find a probable prime with constrained bubble switches. Returning original matrix.")
        return char_matrix, np.zeros_like(char_matrix, dtype=bool), meta

    probable_prime_number = char_matrix_to_big_number(prime_char_matrix)
    swapped_mask = prime_char_matrix != char_matrix
    emit(
        f"Found probable prime with ending {meta['ending']} after {meta['checks']} checks "
        f"and {meta['flips']} bubble flips."
    )
    emit(f"Small-prime sieve rejected {meta['sieve_rejects']} candidates before GMP testing.")
    emit(f"Probable-prime verdict: {_probable_prime(probable_prime_number, rounds=probable_prime_rounds)}")
    return prime_char_matrix, swapped_mask, meta


def render_char_matrix_image(
    char_matrix: np.ndarray,
    bold: bool,
    bgcolor: tuple[int, int, int] | str,
    textcolor: tuple[int, int, int] | str,
    color_matrix: np.ndarray | None = None,
    swapped_mask: np.ndarray | None = None,
    swapped_textcolor: tuple[int, int, int] | str = "#ff0000",
    scale: int = 4,
) -> Image.Image:
    scale = max(1, int(scale))
    num_rows, num_cols = char_matrix.shape
    font_size = 10
    char_width = font_size * 0.6
    line_height = font_size * 0.65
    page_width = num_cols * char_width + 2 * 10
    page_height = num_rows * line_height + 2 * 10

    width = int(math.ceil(page_width * scale))
    height = int(math.ceil(page_height * scale))
    image = Image.new("RGB", (width, height), color=bgcolor)
    draw = ImageDraw.Draw(image)

    try:
        font_name = "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"
        font = ImageFont.truetype(font_name, font_size * scale)
    except Exception:
        font = ImageFont.load_default()

    margin = 10 * scale
    x_step = char_width * scale
    y_step = line_height * scale
    y_position = margin
    stroke_width = max(1, scale // 3) if bold else 0

    base_text_color = _parse_color(textcolor) if isinstance(textcolor, str) else textcolor
    swapped_color = _parse_color(swapped_textcolor) if isinstance(swapped_textcolor, str) else swapped_textcolor

    for row in range(num_rows):
        if color_matrix is None and swapped_mask is None:
            draw.text(
                (margin, y_position),
                "".join(char_matrix[row].tolist()),
                fill=base_text_color,
                font=font,
                stroke_width=stroke_width,
                stroke_fill=base_text_color,
            )
        else:
            x_position = margin
            for col in range(num_cols):
                is_swapped = swapped_mask is not None and bool(swapped_mask[row, col])
                if is_swapped:
                    fill = swapped_color
                elif color_matrix is not None:
                    fill = tuple(int(value) for value in color_matrix[row, col])
                else:
                    fill = base_text_color
                draw.text(
                    (x_position, y_position),
                    char_matrix[row, col],
                    fill=fill,
                    font=font,
                    stroke_width=stroke_width,
                    stroke_fill=fill,
                )
                x_position += x_step
        y_position += y_step

    return image


def write_pdf(
    char_matrix: np.ndarray,
    output_path: Path,
    bold: bool,
    bgcolor: tuple[int, int, int] | str,
    textcolor: tuple[int, int, int] | str,
    color_matrix: np.ndarray | None = None,
    swapped_mask: np.ndarray | None = None,
    swapped_textcolor: tuple[int, int, int] | str = "#ff0000",
) -> tuple[float, float]:
    num_rows, num_cols = char_matrix.shape
    font_size = 10
    char_width = font_size * 0.6
    line_height = font_size * 0.65
    margin = 10
    page_width = num_cols * char_width + 2 * margin
    page_height = num_rows * line_height + 2 * margin
    font_name = "Courier-Bold" if bold else "Courier"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_canvas = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))
    pdf_canvas.setFillColorRGB(bgcolor[0] / 255.0, bgcolor[1] / 255.0, bgcolor[2] / 255.0)
    pdf_canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf_canvas.setFont(font_name, font_size)

    base_text_color = textcolor
    swapped_color = swapped_textcolor

    y_position = page_height - margin
    if color_matrix is None and swapped_mask is None:
        for row in range(num_rows):
            pdf_canvas.setFillColorRGB(base_text_color[0] / 255.0, base_text_color[1] / 255.0, base_text_color[2] / 255.0)
            pdf_canvas.drawString(margin, y_position, "".join(char_matrix[row].tolist()))
            y_position -= line_height
    else:
        for row in range(num_rows):
            for col in range(num_cols):
                is_swapped = swapped_mask is not None and bool(swapped_mask[row, col])
                if is_swapped:
                    pdf_canvas.setFillColorRGB(swapped_color[0] / 255.0, swapped_color[1] / 255.0, swapped_color[2] / 255.0)
                elif color_matrix is not None:
                    color = tuple(int(value) for value in color_matrix[row, col])
                    pdf_canvas.setFillColorRGB(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
                else:
                    pdf_canvas.setFillColorRGB(base_text_color[0] / 255.0, base_text_color[1] / 255.0, base_text_color[2] / 255.0)
                pdf_canvas.drawString(margin + col * char_width, y_position, char_matrix[row, col])
            y_position -= line_height

    pdf_canvas.save()
    return page_width, page_height


def build_output_base_name(image_path: str, suffix: str, matrix_shape: tuple[int, int]) -> str:
    stem = Path(image_path).stem
    height, width = matrix_shape
    suffix_part = f"_{suffix}" if suffix else ""
    return f"{stem}{suffix_part}_{width}x{height}"


def generate_ascii_art(settings: GenerationSettings, logger: Logger | None = None) -> GenerationResult:
    emit = logger or _noop_logger

    image_path = Path(settings.image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    source_image = Image.open(image_path)
    source_width, source_height = source_image.size
    sample_height = max(1, round(settings.sample_width * source_height / source_width))

    resized = source_image.resize((settings.sample_width, sample_height), RESAMPLING_LANCZOS)
    grayscale_image = load_gray_image(resized, settings.grayscale_method, settings.brightness_modifier)
    brightness_values = get_brightness_values(DEFAULT_ALPHABET)
    char_matrix, gray_matrix = get_char_matrix(sample_height, settings.sample_width, grayscale_image, brightness_values)

    prime_requested = bool(settings.enforce_primality)
    prime_found = False
    swapped_mask = np.zeros_like(char_matrix, dtype=bool)
    meta: dict[str, object] = {"checks": 0, "sieve_rejects": 0}

    if prime_requested:
        prime_char_matrix, swapped_mask, meta = enforce_primality(
            char_matrix=char_matrix,
            gray_matrix=gray_matrix,
            brightness_values=brightness_values,
            top_n=settings.top_bubble_pixels,
            max_flips=settings.max_bubble_flips,
            max_checks=settings.max_prime_checks,
            update_interval=settings.update_interval,
            small_prime_limit=settings.small_prime_limit,
            probable_prime_rounds=settings.probable_prime_rounds,
            logger=emit,
        )
        output_suffix = "P"
    else:
        emit("Primality enforcement is disabled.")
        prime_char_matrix = char_matrix
        output_suffix = "C"

    prime_found = bool(prime_requested and not np.array_equal(prime_char_matrix, char_matrix))
    output_base_name = build_output_base_name(settings.image_path, output_suffix, prime_char_matrix.shape)
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    render_swapped_mask = swapped_mask if (prime_requested and settings.highlight_deltas) else None
    background_rgb, color_matrix, text_rgb = _resolve_render_colors(settings, resized)

    output_paths: dict[str, str] = {}
    preview_image = render_char_matrix_image(
        prime_char_matrix,
        bold=settings.bold,
        bgcolor=background_rgb,
        textcolor=text_rgb,
        color_matrix=color_matrix,
        swapped_mask=render_swapped_mask,
        swapped_textcolor=(255, 0, 0),
        scale=settings.jpg_scale,
    )

    if settings.save_pdf:
        pdf_path = output_dir / f"{output_base_name}.pdf"
        write_pdf(
            prime_char_matrix,
            pdf_path,
            bold=settings.bold,
            bgcolor=background_rgb,
            textcolor=text_rgb,
            color_matrix=color_matrix,
            swapped_mask=render_swapped_mask,
            swapped_textcolor=(255, 0, 0),
        )
        output_paths["pdf"] = str(pdf_path)
        emit(f"PDF saved to {pdf_path}")

    if settings.save_jpg:
        jpg_path = output_dir / f"{output_base_name}.jpg"
        preview_image.save(jpg_path, quality=95, subsampling=0)
        output_paths["jpg"] = str(jpg_path)
        emit(f"JPG saved to {jpg_path}")

    if settings.save_txt:
        txt_path = output_dir / f"{output_base_name}.txt"
        with txt_path.open("w", encoding="utf-8") as handle:
            for row in range(prime_char_matrix.shape[0]):
                handle.write("".join(prime_char_matrix[row].tolist()))
                handle.write("\n")
        output_paths["txt"] = str(txt_path)
        emit(f"TXT saved to {txt_path}")

    return GenerationResult(
        char_matrix=prime_char_matrix,
        gray_matrix=gray_matrix,
        source_image=resized,
        swapped_mask=render_swapped_mask if render_swapped_mask is not None else np.zeros_like(prime_char_matrix, dtype=bool),
        preview_image=preview_image,
        output_paths=output_paths,
        output_base_name=output_base_name,
        prime_requested=prime_requested,
        prime_found=prime_found,
        checks=int(meta.get("checks", 0)),
        sieve_rejects=int(meta.get("sieve_rejects", 0)),
        sample_size=(sample_width := settings.sample_width, sample_height),
    )


def rerender_generation_result(settings: GenerationSettings, result: GenerationResult, logger: Logger | None = None) -> GenerationResult:
    emit = logger or _noop_logger

    render_swapped_mask = result.swapped_mask if (result.prime_requested and settings.highlight_deltas) else None
    background_rgb, color_matrix, text_rgb = _resolve_render_colors(settings, result.source_image)
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_paths: dict[str, str] = {}
    preview_image = render_char_matrix_image(
        result.char_matrix,
        bold=settings.bold,
        bgcolor=background_rgb,
        textcolor=text_rgb,
        color_matrix=color_matrix,
        swapped_mask=render_swapped_mask,
        swapped_textcolor=(255, 0, 0),
        scale=settings.jpg_scale,
    )

    if settings.save_pdf:
        pdf_path = output_dir / f"{result.output_base_name}.pdf"
        write_pdf(
            result.char_matrix,
            pdf_path,
            bold=settings.bold,
            bgcolor=background_rgb,
            textcolor=text_rgb,
            color_matrix=color_matrix,
            swapped_mask=render_swapped_mask,
            swapped_textcolor=(255, 0, 0),
        )
        output_paths["pdf"] = str(pdf_path)
        emit(f"PDF saved to {pdf_path}")

    if settings.save_jpg:
        jpg_path = output_dir / f"{result.output_base_name}.jpg"
        preview_image.save(jpg_path, quality=95, subsampling=0)
        output_paths["jpg"] = str(jpg_path)
        emit(f"JPG saved to {jpg_path}")

    if settings.save_txt:
        txt_path = output_dir / f"{result.output_base_name}.txt"
        with txt_path.open("w", encoding="utf-8") as handle:
            for row in range(result.char_matrix.shape[0]):
                handle.write("".join(result.char_matrix[row].tolist()))
                handle.write("\n")
        output_paths["txt"] = str(txt_path)
        emit(f"TXT saved to {txt_path}")

    return GenerationResult(
        char_matrix=result.char_matrix,
        gray_matrix=result.gray_matrix,
        source_image=result.source_image,
        swapped_mask=render_swapped_mask if render_swapped_mask is not None else np.zeros_like(result.char_matrix, dtype=bool),
        preview_image=preview_image,
        output_paths=output_paths,
        output_base_name=result.output_base_name,
        prime_requested=result.prime_requested,
        prime_found=result.prime_found,
        checks=result.checks,
        sieve_rejects=result.sieve_rejects,
        sample_size=result.sample_size,
    )
