       IDENTIFICATION DIVISION.
       PROGRAM-ID. SALES-REPORT.
       AUTHOR. MMIM-TEST.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUSTOMER-NAME       PIC X(30).
       01  WS-CUSTOMER-TYPE       PIC X.
       01  WS-QUANTITY             PIC 9(5).
       01  WS-UNIT-PRICE           PIC 9(7)V99.
       01  WS-SUBTOTAL             PIC 9(9)V99.
       01  WS-DISCOUNT             PIC 9(7)V99.
       01  WS-TAX                  PIC 9(7)V99.
       01  WS-TOTAL                PIC 9(9)V99.
       01  WS-GRAND-TOTAL          PIC 9(10)V99 VALUE 0.
       01  WS-ORDER-COUNT          PIC 9(4) VALUE 0.
       01  WS-DISCOUNT-RATE        PIC 9V99 VALUE 0.
       01  WS-TAX-RATE             PIC 9V99 VALUE 0.18.
       01  WS-CONTINUE             PIC X VALUE 'Y'.
       01  WS-STATUS               PIC X(12).
       01  WS-CATEGORY             PIC X(10).

       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY '*** SALES ORDER PROCESSOR ***'.
           PERFORM INITIALIZE-DATA.
           PERFORM PROCESS-ORDER.
           PERFORM DISPLAY-SUMMARY.
           STOP RUN.

       INITIALIZE-DATA.
           MOVE 'GENERAL' TO WS-CATEGORY.
           MOVE 0 TO WS-GRAND-TOTAL.
           MOVE 0 TO WS-ORDER-COUNT.
           MOVE 'Y' TO WS-CONTINUE.
           MOVE 'READY' TO WS-STATUS.
           DISPLAY 'SYSTEM STATUS: ' WS-STATUS.

       PROCESS-ORDER.
           DISPLAY 'ENTER CUSTOMER NAME:'.
           ACCEPT WS-CUSTOMER-NAME.
           DISPLAY 'ENTER CUSTOMER TYPE (R/B):'.
           ACCEPT WS-CUSTOMER-TYPE.
           DISPLAY 'ENTER QUANTITY:'.
           ACCEPT WS-QUANTITY.
           DISPLAY 'ENTER UNIT PRICE:'.
           ACCEPT WS-UNIT-PRICE.
           PERFORM CALCULATE-ORDER.
           PERFORM APPLY-DISCOUNT.
           PERFORM CALCULATE-TAX.
           PERFORM FINALIZE-ORDER.

       CALCULATE-ORDER.
           COMPUTE WS-SUBTOTAL = WS-QUANTITY * WS-UNIT-PRICE.
           IF WS-SUBTOTAL > 10000
               MOVE 'PREMIUM' TO WS-CATEGORY
           ELSE
               MOVE 'STANDARD' TO WS-CATEGORY
           END-IF.
           DISPLAY 'CUSTOMER: ' WS-CUSTOMER-NAME.
           DISPLAY 'CATEGORY: ' WS-CATEGORY.
           DISPLAY 'SUBTOTAL CALCULATED'.
           ADD 1 TO WS-ORDER-COUNT.

       APPLY-DISCOUNT.
           MOVE 0 TO WS-DISCOUNT-RATE.
           IF WS-CUSTOMER-TYPE = 'R'
               MOVE 0.10 TO WS-DISCOUNT-RATE
           ELSE
               IF WS-CUSTOMER-TYPE = 'B'
                   MOVE 0.15 TO WS-DISCOUNT-RATE
               ELSE
                   MOVE 0 TO WS-DISCOUNT-RATE
               END-IF
           END-IF.
           COMPUTE WS-DISCOUNT = WS-SUBTOTAL * WS-DISCOUNT-RATE.
           SUBTRACT WS-DISCOUNT FROM WS-SUBTOTAL.
           DISPLAY 'DISCOUNT APPLIED'.

       CALCULATE-TAX.
           COMPUTE WS-TAX = WS-SUBTOTAL * WS-TAX-RATE.
           COMPUTE WS-TOTAL = WS-SUBTOTAL + WS-TAX.
           IF WS-TOTAL >= 50000
               MOVE 'HIGH VALUE' TO WS-STATUS
           ELSE
               MOVE 'NORMAL' TO WS-STATUS
           END-IF.
           DISPLAY 'TAX CALCULATED'.
           DISPLAY 'ORDER STATUS: ' WS-STATUS.

       FINALIZE-ORDER.
           ADD WS-TOTAL TO WS-GRAND-TOTAL.
           DISPLAY 'ORDER TOTAL: ' WS-TOTAL.
           IF WS-TOTAL = 0
               DISPLAY 'WARNING: ZERO VALUE ORDER'
           ELSE
               DISPLAY 'ORDER ACCEPTED'
           END-IF.
           IF WS-ORDER-COUNT >= 10
               DISPLAY 'ORDER LIMIT REACHED'
           END-IF.

       DISPLAY-SUMMARY.
           DISPLAY '------------------------------'.
           DISPLAY 'SALES PROCESSING SUMMARY'.
           DISPLAY 'CUSTOMER: ' WS-CUSTOMER-NAME.
           DISPLAY 'ORDERS PROCESSED: ' WS-ORDER-COUNT.
           DISPLAY 'GRAND TOTAL: ' WS-GRAND-TOTAL.
           DISPLAY 'FINAL STATUS: ' WS-STATUS.
           DISPLAY '------------------------------'.
           MOVE 'COMPLETE' TO WS-STATUS.
           DISPLAY 'PROCESSING STATUS: ' WS-STATUS.
           STOP RUN.
