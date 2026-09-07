       IDENTIFICATION DIVISION.
       PROGRAM-ID. MISLEADCM.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
      * BUSINESS RULE: VIP customers receive a 20 percent discount.
      * (The code below does NOT implement any discount.)
       01 WS-CUSTOMER-TYPE PIC X VALUE 'V'.
       01 WS-PRICE         PIC 9(5) VALUE 1000.
       01 WS-FINAL-PRICE   PIC 9(5) VALUE 0.
       PROCEDURE DIVISION.
       MAIN-PARA.
           MOVE WS-PRICE TO WS-FINAL-PRICE.
           DISPLAY WS-FINAL-PRICE.
           STOP RUN.
