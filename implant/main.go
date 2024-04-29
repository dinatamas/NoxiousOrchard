package main

import (
  "io"
  "log"
  "net"
  "os"
  "sync"
  "time"
)

const (
  LHOST = "127.0.0.1"
  LPORT = "33443"
)

func main() {
  // Todo: handle interrupts!
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

      remote_buffer := make(chan []byte)
      local_buffer := make(chan []byte)

      var wg sync.WaitGroup

      wg.Add(1)
      go func() {
        gorecv("remote", conn, remote_buffer)
        wg.Done()
      }()

      wg.Add(1)
      go func() {
        gosend("remote", remote_buffer, os.Stdout)
        wg.Done()
      }()

      wg.Add(1)
      go func() {
        gorecv("local", os.Stdin, local_buffer)
        wg.Done()
      }()

      wg.Add(1)
      go func() {
        gosend("local", local_buffer, conn)
        wg.Done()
      }()

      wg.Wait()
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
