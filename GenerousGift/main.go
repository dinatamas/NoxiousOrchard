package main

import (
  "bufio"
  "io"
  "log"
  "net"
  "os"
  "time"
)

const (
  LHOST = "127.0.0.1"
  LPORT = "33443"
)

func main() {
  // Todo: Handle interrupts!
  os.Exit(_main())
}

func _main() int {
  log.SetFlags(0)
  alive := true

  for alive {
    func() {
      conn, err := net.Dial("tcp", LHOST + ":" + LPORT)
      if err != nil {
        log.Print("connection error: ", err)
        time.Sleep(1 * time.Second)
        return
      }
      defer conn.Close()

      connbuf := bufio.NewReader(conn)

      for alive {
        // Todo: Handle LF and CRLF as well!
        cmd, err := connbuf.ReadString('\n')
        if err != nil {
          if err != io.EOF {
            log.Print("cmdloop error: ", err)
          }
          return
        }
        cmd = cmd[:len(cmd)-1]
        log.Print("executing command: ", cmd)
        if cmd == "kill" {
          alive = false
        }
        // Todo: Placeholder for command parsing!
        // Todo: Or: should I just use JSON?
        // Todo: Or: should I use XML / ASN.1?
        // Todo: Or: some sort of HTTP?
        else {
          log.Print("unknown command")
        }
      }
    }()
  }

  return 0
}







func gorecv(name string, fd io.Reader, send chan<- []byte) {
  defer close(send)
  for {
    buf := make([]byte, 4096)
    n, err := fd.Read(buf)
    if err != nil {
      if err != io.EOF {
        log.Printf("gorecv %s: error %s", name, err)
      }
      log.Printf("gorecv %s: finished", name)
      return
    }
    send <- buf[:n]
  }
}

func gosend(name string, recv <-chan []byte, fd io.Writer) {
  for {
    select {
      case buf, ok := <-recv:
        if !ok {
          log.Printf("gosend %s: finished", name)
          return
        }
        fd.Write(buf)
    }
  }
}
