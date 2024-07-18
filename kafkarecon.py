#!/usr/bin/env python3
"""
Reconnaissance and enumeration tool for Apache Kafka.
"""
from dataclasses import asdict, dataclass
import csv
import functools
import io
import math
import operator
import os
import re
import sys
import subprocess
import traceback
from uuid import uuid4

from confluent_kafka import (
    Consumer,
    KafkaException,
    TopicCollection,
)
from confluent_kafka.admin import (
    AdminClient,
    ConfigResource,
)


DEBUG = True
# TODO: os.path.join
# TODO: makedir -p
OUTDIR = "logs"


@dataclass
class _AdminConfig:
    bootstrap_servers: str = "eric-data-message-bus-kf-0.eric-data-message-bus-kf.esm.svc.cluster.local:9093"
    security_protocol: str = "SSL"
    ssl_ca_location: str = "ca-bundle.pem"
    ssl_certificate_location: str = "cert.pem"
    ssl_key_location: str = "key.pem"
    enable_ssl_certificate_verification: bool = False
AdminConfig = _AdminConfig()


@dataclass
class _ConsumerConfig(_AdminConfig):
    group_id: str = ""
ConsumerConfig = _ConsumerConfig()


def main():
    kubedns = subprocess.check_output("kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}'", shell=True).decode()
    os.system(f"echo 'nameserver {kubedns}' | sudo tee -a /etc/resolv.conf")
    container = subprocess.check_output("docker ps --format '{{.Names}}' | grep syslog-gateway_syslog-gateway", shell=True).decode()[:-1]
    os.system(f"docker cp -L {container}:/etc/ssl/mtls/ca-bundle.pem ./")
    os.system(f"docker cp -L {container}:/etc/ssl/mtls/messagebus-kf/cert.pem ./")
    os.system(f"docker cp -L {container}:/etc/ssl/mtls/messagebus-kf/key.pem ./")

    # ===========================================
    # -- Tool Configuration --
    # ===========================================

    print_title("Tool Configuration")
    print()

    if not ConsumerConfig.group_id:
        ConsumerConfig.group_id = uuid4().hex
        print_info(f"No consumer group ID provided -> using: {ConsumerConfig.group_id}")

    admin_config = {key.replace("_", "."): value for key, value in asdict(AdminConfig).items()}
    consumer_config = {key.replace("_", "."): value for key, value in asdict(ConsumerConfig).items()}
    print_table(("Name", "Value"), *consumer_config.items())
    print()
    try:
        ADMIN = AdminClient(admin_config)
        print_success("Admin client connected")
    except KafkaException as e:
        print_error(f"Admin client connection failed: {e}")
        print_debug(traceback.format_exc())
        return
    try:
        CONSUMER = Consumer(consumer_config)
        print_success("Consumer connected")
    except KafkaException as e:
        print_error(f"Consumer connection failed: {e}")
        print_debug(traceback.format_exc())
        return

    # ===========================================
    # -- Cluster Nodes --
    # ===========================================

    print_title("Cluster Nodes")
    print()

    CLUSTER = ADMIN.describe_cluster(request_timeout=15).result()
    print_info(f"Cluster ID: {CLUSTER.cluster_id}")

    is_controller = lambda i: f"{GREEN}{BOLD}#{i} [C]{RESET}" if i == CLUSTER.controller.id else f"#{i}"
    print_table(
        ("Broker", "Hostname", "Port", "Rack"),
        *((is_controller(n.id), n.host, n.port, n.rack) for n in CLUSTER.nodes)
    )

    # ===========================================
    # -- Broker Configuration --
    # ===========================================

    print_title("Broker Configuration")
    print()

    META = ADMIN.list_topics(timeout=15)

    def config_to_table(entries):
        entries = dict(sorted(entries.items()))
        entry_header = ["Name", "Value", "Source", "Writable", "Default", "Sensitive"]
        entry_to_row = lambda e: [e.name, e.value, e.source, not e.is_read_only, e.is_default, e.is_sensitive]
        entry_table = [entry_to_row(e) for e in entries.values() if not e.is_default and e.value]
        full = list(map(entry_to_row, entries.values()))
        return ([entry_header, *entry_table], {"format": ".TcYHY", "color": "...EE"}), full

    print_info(f"Metadata origin broker ID: {META.orig_broker_id}")
    print_info(f"Metadata origin broker name: {META.orig_broker_name}")

    for broker in META.brokers.values():
        resource = ConfigResource(ConfigResource.Type.BROKER, str(broker.id))
        entries = ADMIN.describe_configs([resource])[resource].result()
        (args, kwargs), full = config_to_table(entries)
        if broker.id == CLUSTER.controller.id:
            print_table(*args, **kwargs)
        csvfile = f"{OUTDIR}/broker-{broker.id}.csv"
        dump_csv(csvfile, *full)
        print()
        print_success(f"Dumped full broker #{broker.id} configuration table to '{csvfile}'")

    # ===========================================
    # -- Topic Overview --
    # ===========================================

    print_title("Topic Overview")
    print()

    names = sorted(list(META.topics.keys()))
    topics = ADMIN.describe_topics(TopicCollection(names), request_timeout=15)
    topics = dict(sorted((k, v.result()) for k, v in topics.items()))
    external = sorted([t.name for t in topics.values() if not t.is_internal])

    resources = [ConfigResource(ConfigResource.Type.TOPIC, t) for t in external]
    results = {k.name: v.result() for k, v in ADMIN.describe_configs(resources).items()}
    for name, res in results.items():
        (args, kwargs), full = config_to_table(res)
        # print_table(*args, **kwargs)
        # print_table(["Config", "Something"], *list(res.items()))
        # print_table(["Config", "Something"], *full)
        dump_csv(f"{OUTDIR}/topic-{name}.csv", *full)
        break
    print_success(f"Dumped full topic configuration tables to 'topic-<topicname>.csv'")

    def err_to_str(err):
        return f"{err.code()} -> {err.name()} = {err.str()}"

    # https://github.com/confluentinc/librdkafka/blob/master/src-cpp/rdkafkacpp.h
    terrs, perrs = dict(), dict()
    for topic in META.topics.values():
        if topic.error:
            terrs[topic.topic]
        for part in topic.partitions.values():
            if part.error:
                perrs[f"{topic.topic}/{part.id}"] = part.error

    is_compacted = lambda name: f"{name} {BLUE}{BOLD}[C]{RESET}" if results[name]["cleanup.policy"].value == "compact" else name
    def is_compacted(name):
        cp = results[name]["cleanup.policy"].value
        if cp == "delete": return name
        if cp == "compact": return f"{name} {BLUE}{BOLD}[C]{RESET}"
        if cp == ("compact,delete", "delete,compact"): return f"{name} {BLUE}{BOLD}[CD]{RESET}"
    print_table(
        ["Topic ID", "Name", "Error", "Partitions", "Min ISRs", "Retention", "Segment"],
        *[(
            t.topic_id, is_compacted(name), name in terrs, len(t.partitions),
            results[name]["min.insync.replicas"].value,
            f"{guess_storage(results[name]['retention.bytes'].value)} | {guess_duration(results[name]['retention.ms'].value)}",
            f"{guess_storage(results[name]['segment.bytes'].value)} | {guess_duration(results[name]['segment.ms'].value)}",

        ) for name, t in topics.items() if not t.is_internal],
        format="U.Y....")

    print()
    if terrs:
        for name, err in terrs.items():
            print_error(f"{name} TOPIC error {err_to_str(err)}")
    else:
        print_success("No TOPIC errors")

    print()
    if perrs:
        for name, err in perrs.items():
            print_error(f"{name} PARTITION error {err_to_str(err)}")
    else:
        print_success("No PARTITION errors")

    # ===========================================
    # -- Broker Partition Tables --
    # ===========================================

    print_title(f"Broker Partitions")
    print()
    print_info("Legend for broker partition tables:")
    print_info("L : leader", level=1)
    print_info("i : in-sync replica", level=1)
    print_info("r : out-of-sync replica", level=1)
    print_info("e : error", level=1)
    print_info("? : no leader", level=1)
    print_info("- : no partition", level=1)
    rows = []
    width = max(len(t.partitions) for t in topics.values())
    for bid in META.brokers.keys():
        for name, topic in sorted(META.topics.items()):
            if topics[name].is_internal or name in terrs:
                continue
            parts = []
            for part in topic.partitions.values():
                if part.error:
                    parts.append(f"{RED}{BOLD}e{RESET}")
                elif part.leader == -1:
                    parts.append(f"{YELLOW}{BOLD}?{RESET}")
                elif bid == part.leader:
                    parts.append(f"{GREEN}{BOLD}L{RESET}")
                elif bid in part.isrs:
                    parts.append("i")
                elif bid in part.replicas:
                    parts.append("r")
                else:
                    parts.append(".")
            rows.append([topic.topic, " ".join(parts) + " " + " ".join(["-" for _ in range(width - len(parts))])])
        print_table([f"Broker #{bid}", " ".join([str(w % 10 or ".") for w in range(width)])], *rows)

    # ===========================================
    # -- Topic Contents --
    # ===========================================

    # TODO: At this point start looking into partition + consumer group offsets!
    # TODO: Also describe this debug consumer's group!
    # Then display topic / partition content size, e.g.
    # Then when you know what to expect for each partition -> assign, read.
    # Get 3 messages from all partitions -> dump them.
    # But then only display a couple per topic (randomly) for topics that have ~50 partitions!
    # Full / larger data dump in background thread?

    if DEBUG:
        return

    def on_assign(cons, parts):
        for part in parts:
            _, high = cons.get_watermark_offsets(part)
            part.offset = max(high - 3, 0)
        cons.assign(parts)
        cons.pause(parts)

    CONSUMER.subscribe(external, on_assign=on_assign)
    CONSUMER.poll(1.0)
    parts = CONSUMER.assignment()
    for part in parts:
        print(part)
        CONSUMER.resume([part])
        msg = CONSUMER.poll(5.0)
        if msg:
            print(msg.value())
        msg = CONSUMER.poll(5.0)
        if msg:
            print(msg.value())
        msg = CONSUMER.poll(5.0)
        if msg:
            print(msg.value())
        CONSUMER.pause([part])
        sys.stdout.flush()


def guess_storage(value, unit="b"):
    def r(v): return f"{round(v, int(math.log10(v)) or 2):g}"
    def R(v): return "~" * (float(v) != float(r(v))) + r(v)
    if float(value) < 0: return "N/A"
    if float(value) == 0: return "0 bytes"
    value = float(value) * (1000 + 24 * (unit[-1] == "i")) ** "bKMGT".find(unit[0])
    for i, su in zip(range(1, 5), "KMGT"):
        B, IB = value / 1000 ** i, value / 1024 ** i
        Be, IBe = abs(round(B) - B), abs(round(IB) - IB)
        Bl, IBl = str(B)[::-1].find('.'), str(IB)[::-1].find('.')
        if IB <= 102.4:
            if i == 1 and B < 10 and 0 not in (Be, IBe): return f"{int(value)} bytes"
            return f"{R(B)} {su}B" if Bl < 2 or (Be < IBe and IBl > 2) else f"{R(IB)} {su}iB"
    return ValueError(f"Too big storage: {value}")  # TODO: Handle this with largest unit!


def guess_duration(value, unit="ms"):
    def r(v): return f"{round(v, 1):g}"
    def R(v): return "~" * (float(v) != float(r(v))) + r(v)
    UNITS, RATES = ["ms", "s", "m", "h", "d"], [1, 1000, 60, 60, 24]
    if float(value) <= 0: return "N/A"
    value = float(value) * functools.reduce(operator.mul, RATES[:UNITS.index(unit) + 1])
    for unit, rate in zip(UNITS, RATES[1:]):
        if value < rate:
            return f"{R(value)} {unit}"
        value = value / rate
    return f"{R(value)} {UNITS[-1]}"


def print_title(title, width=80):
    title = astr(title)
    line = "=" * max(len(title) + 4, width)
    text = f"- {title} -".center(width, " ")
    printO(f"\n{BOLD}{line}\n{GREEN}{text}{WHITE}\n{line}{RESET}")
    printE(f"\n{line}\n{text}\n{line}")


# TODO: Consider another table format.
#
# | Title 1   | Title 2   |
# |-----------|-----------|
# | value 1-1 | value 1-2 |
# | value 2-1 | value 2-2 |
#
def print_table(*rows, format=None, color=None):
    if format is not None: rows = format_table(*rows, mask=format)
    if color is not None: rows = color_table(*rows, mask=color)
    rows = [[astr(v) for v in row] for row in rows]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    formatted = [rows[0], ["-" * len(header) for header in rows[0]], *rows[1:]]
    formatted = [("   " + "  ".join([cell.ljust(width) for cell, width in zip(r, widths)])) for r in formatted]
    print()
    printO(BOLD + formatted[0] + RESET); printE(formatted[0])
    printO(BOLD + formatted[1] + RESET); printE(formatted[1])
    [print(row) for row in formatted[2:]]
    sys.stdout.flush()


def format_table(*rows, mask):
    """
        . | leave as-is
        R | repr()
        S | str() or "-"
        T | truncated to 40
        Y | yes-empty boolean 
        y | yes-no boolean
        H | hidden
        u | confluent_kafka.UUID
        c | confluent_kafka.admin.ConfigSource
    """
    return [[(v if i == 0 else {
        ".": lambda v: str(v),
        "R": lambda v: repr(v),
        "S": lambda v: str(v or "-"),
        "T": lambda v: astr(v or "-")[:37] + ("..." if len(astr(v)) > 37 else ""),
        "Y": lambda v: "Yes" if v else "-",
        "y": lambda v: "Yes" if v else "No",
        "U": lambda v: f"{hex(v.get_most_significant_bits())}-{hex(v.get_least_significant_bits())}",
        "c": lambda v: ["UUU", "D.T", "D.B", "DdB", "..B", ".d."][v],
    }[m](v)) for m, v in zip(mask, r) if m != "H"]
    for i, r in enumerate(rows)]


def color_table(*rows, mask):
    """
        .           | leave as-is
        r,g,y,b,m,c | corresponding color
        R,G,Y,B,M,C | corresponding color + bold
        E           | Yes -> R, "-"/No -> g
        e           | Yes -> G, "-"/No -> .
    """
    # Note: If the format has hidden fields, disregard them in the color mask!
    return [[(v if i == 0 else {
        ".": lambda v: v,
        "E": lambda v: f"{RED}{BOLD}Yes{RESET}" if v == "Yes" else v,
        "e": lambda v: f"{GREEN}{BOLD}Yes{RESET}" if v == "Yes" else v,
    }[m](v)) for m, v in zip(mask, r)]
    for i, r in enumerate(rows)]


def dump_csv(path, *rows, format=None):
    if format is not None: rows = format_table(*rows, mask=format)
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


class astr(str):
    ANSI_RE = re.compile(r"\033\[\d+m")

    @functools.cached_property
    def clean(self):
        return self.ANSI_RE.sub("", self)

    @functools.cached_property
    def ldiff(self):
        return super().__len__() - len(self.clean)

    def __len__(self): return len(self.clean)
    def __getitem__(self, key): return self.clean[key]
    def center(self, width, fc=" "): return super().center(width + self.ldiff, fc)
    def ljust(self, width, fc=" "): return super().ljust(width + self.ldiff, fc)
    def rjust(self, width, fc=" "): return super().rjust(width + self.ldiff, fc)


BOLD    = "\033[1m"
BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"
RESET   = "\033[0m"
def print_debug(msg):   print(msg, file=sys.stderr)
def print_error(msg, level=0):   l33t_pR1N7(msg, level, RED,    "-")
def print_warning(msg, level=0): l33t_pR1N7(msg, level, YELLOW, "!")
def print_success(msg, level=0): l33t_pR1N7(msg, level, GREEN,  "+")
def print_info(msg, level=0):    l33t_pR1N7(msg, level, BLUE,   "*")
def l33t_pR1N7(msg, level, color, symbol):
    lvl = " " + (level - 1) * "   " + "└─" if level else ""
    printO(f"{color}{lvl}[{symbol}]{RESET} {msg}")
    printE(f"{lvl}[{symbol}] {msg}");


def ask_input(msg, dflt=None):
    dflt_string = f" ({dflt})" if dflt is not None else ""
    printO(f"{CYAN}[?]{RESET} {msg}{dflt_string} ", end="")
    printE(f"[?] {msg}{dflt_string}: ", end="")
    res = (input() or dflt)
    print(res, file=sys.stderr)
    sys.stdout.flush()
    return res


def printO(text, end="\n"):
    if isinstance(sys.stdout, tee):
        sys.stdout.stdout.write(text + end)
    else:
        sys.stdout.write(text + end)
    sys.stdout.flush()


def printE(text, end="\n"):
    if isinstance(sys.stdout, tee):
        sys.stdout.stderr.write(text + end)
        sys.stdout.stderr.flush()


class tee:
    def __init__(self, stdout, stderr):
        self.stdout = stdout
        self.stderr = stderr

    def write(self, text):
        self.stdout.write(text)
        self.stderr.write(astr(text).clean)

    def flush(self):
        self.stdout.flush()
        self.stderr.flush()


# https://eli.thegreenplace.net/2015/redirecting-all-kinds-of-stdout-in-python/
#  - Redirect libc's stdout and stderr to the log file.
#  - Redirect Python's stderr to the log file.
#  - Duplicate Python's stdout to both the terminal and the log file.
# It is not possible to redirect stdout from libraries, which requires redirecting the
# libc stdout file descriptor, while also using the Python readline module (which only
# enters interactive mode if the libc stdout is a TTY).
# https://bugs.python.org/issue512981#msg393561
def _main():
    err = None
    LOGFILE = f"{OUTDIR}/log.txt"
    tfile = open(LOGFILE, "w+b")
    tfileio = io.TextIOWrapper(tfile)
    LIBC_STDOUT_FD = sys.stdout.fileno()
    LIBC_STDERR_FD = sys.stderr.fileno()
    SAVED_STDOUT_FD = os.dup(LIBC_STDOUT_FD)
    SAVED_STDERR_FD = os.dup(LIBC_STDERR_FD)
    saved_stdout = io.TextIOWrapper(os.fdopen(SAVED_STDOUT_FD, "wb"))
    try:
        os.dup2(tfile.fileno(), LIBC_STDOUT_FD)
        os.dup2(tfile.fileno(), LIBC_STDERR_FD)
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = tee(saved_stdout, tfileio)
        sys.stderr = tfileio
        print()
        print_info(f"Logging to {os.path.abspath(LOGFILE)}")
        main()
    except BaseException as e:
        err = e
    finally:
        os.dup2(SAVED_STDOUT_FD, LIBC_STDOUT_FD)
        os.dup2(SAVED_STDERR_FD, LIBC_STDERR_FD)
        sys.stdout = io.TextIOWrapper(os.fdopen(LIBC_STDOUT_FD, "wb"))
        sys.stderr = io.TextIOWrapper(os.fdopen(LIBC_STDERR_FD, "wb"))
        saved_stdout.close()
        tfileio.close()
        tfile.close()
    if err:
        raise err


if __name__ == "__main__":
    try:
        _main()
    except (AssertionError, KeyboardInterrupt):
        print("\x08\x08  ")  # Stop ^C from popping up.
        print_warning("Execution aborted, exiting...")
    except Exception as e:
        print_error(f"Encountered exception: {e}")
        if DEBUG:
            raise e
