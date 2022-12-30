~~~~
                            , _
 () o  _,        _,  |\    /|/_)o |\  _|   _          _   ,_ _|_
 /\ | / | /|/|  / |  |/     |  \| |/ / |  |/ /\/ |/\_/ \_/  | |
/(_)|/\/|/ | |_/\/|_/|_/    |(_/|/|_/\/|_/|_/ /\/|_/ \_/    |/|_/
       (|                                       (|
~~~~

![demo](demo.jpeg)

## Why «Signal Bildexport» had to be done

Ever wanted to save images from **Signal** messages? It is a chore:

- Every **single photo** needs to be **exported separately**
- All metadata is lost – and even with a **wrong Timestamp**. This messes up your (iCloud) photo timeline!

Unlike Whatsapp, Signal does not provide automatic saving of received images to the camera roll. The discussion is still going on:

- Github Feature Request #1567: [Option to auto-save received images/video to camera roll](https://github.com/signalapp/Signal-iOS/issues/1567)
- Signal Community Discussion Thread: [Automatically save attachments to device](https://community.signalusers.org/t/automatically-save-attachments-to-device-and-possibly-link-to-them-from-inside-the-app/5147)

Due to this hassle, friends and family were **threatening to switch back** from **Signal** to **Whatsapp**. Things were getting serious! But, fear not:

## What «Signal Bildexport» does

Since the images cannot be saved directly from Android/iOS, this script **exports photos from** **Signal Desktop** on Mac or Windows to a chosen **folder** or **iCloud Photos**

1. Reads Signal Desktop's encrypted sqlite database
2. Collects all messages which were received (since Signal Desktop was installed)
3. Exports every found JPEG Photo to the *iCloud Photos* folder (Windows) or the *Photos* App (Mac) with the following metadata annotations:
   - Timestamp (the closed we can get: the instant when the picture was sent)
   - Who send it (Full contact name or Signal Name, if not in contacts)
   - Name of the Chat group
   - The message that came with it as the image's title

Installation on Windows
-------

#### Prerequisites

- iCloud for Windows is installed
- Signal Desktop is installed and configured (and some Photos have been received already)

#### Powershell

~~~~powershell
wsl --install
~~~~

#### Bash

~~~~bash
sudo apt-get update  
apt-get install python3-pip  
pip install -r requirements.txt
sudo apt install libsqlite3-dev tclsh libssl-dev
git clone https://github.com/sqlcipher/sqlcipher.git
cd sqlcipher
./configure --enable-tempstore=yes CFLAGS="-DSQLITE_HAS_CODEC" LDFLAGS="-lcrypto -lsqlite3"
make && sudo make install
~~~~

## Installation on Mac

#### Prerequisites

- Signal Desktop is installed and configured (and some Photos have been received already)

#### Terminal (zsh or bash)

~~~~bash
pip install -r requirements.txt
brew install sqlcipher
pip install pysqlcipher3
~~~~
