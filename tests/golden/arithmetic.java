public class ArithmeticTest {

    private int numA = 10;
    private int numB = 5;

    public static void main(String[] args) {
        new ArithmeticTest().run();
    }

    public void run() {

        numB += numA;
        numB -= 2;
        numB *= numA;
        numB /= 3;
        return;

    }

}
