~~~~
                            , _
 () o  _,        _,  |\    /|/_)o |\  _|   _          _   ,_ _|_
 /\ | / | /|/|  / |  |/     |  \| |/ / |  |/ /\/ |/\_/ \_/  | |
/(_)|/\/|/ | |_/\/|_/|_/    |(_/|/|_/\/|_/|_/ /\/|_/ \_/    |/|_/
       (|                                       (|
~~~~

Windows
-------

### Powershell

~~~~
$ wsl --install
~~~~

### Bash

~~~~
$ sudo apt-get update  
$ apt-get install python3-pip  
$ pip install -r requirements.txt
$ sudo apt install libsqlite3-dev tclsh libssl-dev
$ git clone https://github.com/sqlcipher/sqlcipher.git
$ cd sqlcipher
$ ./configure --enable-tempstore=yes CFLAGS="-DSQLITE_HAS_CODEC" LDFLAGS="-lcrypto -lsqlite3"
$ make && sudo make install
~~~~
