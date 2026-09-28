import csv
from collections import defaultdict

INPUT_CSV = "C:/Users/User/Downloads/Telegram Desktop/files/kuvasoy_tarmok_pipe_coordinates.csv"
OUTPUT_PIPES = "generated_pipes.py"

def read_pipe_routes(csv_path):
    pipes = defaultdict(list)

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            pipe_index = str(row["pipe_index"]).strip()
            line_index = str(row["line_index"]).strip()
            point_order = int(row["point_order"])
            lon = float(row["lon"])
            lat = float(row["lat"])

            key = (pipe_index, line_index)
            pipes[key].append((point_order, lat, lon))

    result = {}
    for key, points in pipes.items():
        points_sorted = sorted(points, key=lambda x: x[0])
        route = [[lat, lng] for _, lat, lng in points_sorted]
        result[key] = route

    return result

def build_pipes_block(pipe_routes):
    lines = []
    lines.append("from typing import Dict\n")
    lines.append("PIPES: Dict[str, Dict] = {")

    counter = 1
    for (pipe_index, line_index), route in pipe_routes.items():
        pipe_id = f"P{counter}"
        name = f"Труба {pipe_index}-{line_index}"

        route_text = ", ".join(f"[{lat:.14f}, {lng:.14f}]" for lat, lng in route)

        lines.append(f'    "{pipe_id}": {{')
        lines.append(f'        "id": "{pipe_id}",')
        lines.append(f'        "from": None,')
        lines.append(f'        "to": None,')
        lines.append(f'        "name": "{name}",')
        lines.append(f'        "road_hint": "Кувасой шаҳар",')
        lines.append(f'        "route": [{route_text}],')
        lines.append(f'    }},')

        counter += 1

    lines.append("}")
    return "\n".join(lines)

def main():
    pipe_routes = read_pipe_routes(INPUT_CSV)
    print(f"Найдено линий труб: {len(pipe_routes)}")

    pipes_text = build_pipes_block(pipe_routes)

    with open(OUTPUT_PIPES, "w", encoding="utf-8") as f:
        f.write(pipes_text)

    print(f"Готово. Сохранено в {OUTPUT_PIPES}")

if __name__ == "__main__":
    main()